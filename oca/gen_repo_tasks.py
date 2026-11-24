"""Multi-file `repo_pytest` task synthesis & automated pytest triple-control verification.

Generates realistic 4-6 file Python mini-repositories (`src/<pkg>/...` + visible `tests/test_smoke.py`
+ hidden `tests_hidden/test_hidden.py`) with cross-module bugs, verified immediately via `oca.validate.check_repo_task`:
  - `original` fails hidden pytest
  - `partial` fixes >=1 bug and passes strictly more hidden tests than `original` while still failing
  - `reference` passes 100% of both visible `tests/` and hidden `tests_hidden/` (>=8 tests)
  - Strict domain-disjoint train/heldout split (zero cross-split domain leakage)

Uses strong OpenCode Go models (`deepseek-v4.1-flash` or `gemini-4-argon`) with sticky `x-opencode-session`
prompt caching and SHA-256 disk response caching under `.cache/repo_gen/`.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import re
import shutil
import threading
import time
import urllib.error
import urllib.request

from . import ROOT
from .validate import check_repo_task

OPENAI_GO_URL = "https://opencode.ai/inference/go/openai/v1/chat/completions"
GOOGLE_GO_URL = "https://opencode.ai/inference/go/google/v1beta/models/{model}:generateContent"
CACHE_DIR = ROOT / ".cache" / "repo_gen"

# 18 distinct multi-file software engineering domains (5 heldout domains, 13 train domains — 100% disjoint)
REPO_DOMAINS = [
    ("r01", "mini_orm", "train", "Tiny in-memory queryable table/ORM: schema definitions, filter predicates, join/order/limit query engine"),
    ("r02", "config_cascade", "train", "Layered YAML-lite/INI config loader: file resolver, inheritance & env interpolation, validation layer"),
    ("r03", "workflow_dag", "train", "DAG task runner: node/edge parser, topological planner with retries & skip propagation, execution ledger"),
    ("r04", "http_router", "train", "HTTP URL router & middleware chain: path-param/wildcard trie, method dispatch, middleware pipeline"),
    ("r05", "rate_quota", "train", "Multi-tenant rate & quota service: policy definitions, token-bucket/sliding-window stores, hierarchical enforcer"),
    ("r06", "template_kit", "train", "Mini template engine: lexer/parser for `{{ var }}` / `{% if %}` / `{% for %}`, filter registry, renderer"),
    ("r07", "ledger_book", "train", "Double-entry accounting ledger: account chart, journal posting validator, trial-balance & statement generator"),
    ("r08", "pkg_resolver", "train", "Semver package dependency resolver: version constraint parser, conflict detector, lockfile planner"),
    ("r09", "event_bus", "train", "Pub/sub event broker: topic wildcard matcher, dead-letter retry queue, consumer group offset tracker"),
    ("r10", "doc_indexer", "train", "Mini full-text search index: tokenizer/stemmer, inverted index builder, boolean+phrase query ranker"),
    ("r11", "csv_etl", "train", "Tabular ETL pipeline: dialect parser, column transform/cast operators, group-by aggregator & schema checker"),
    ("r12", "cache_proxy", "train", "Multi-tier cache engine: TTL/tag invalidation registry, LRU/LFU eviction policy, write-through coordinator"),
    ("r13", "cron_sched", "train", "Cron & job scheduler: cron expression parser, calendar/blackout evaluator, next-run & conflict planner"),
    # Strictly heldout engineering domains (never seen in training)
    ("r14", "patch_vcs", "heldout", "Mini diff/patch toolkit: hunk parser, 3-way merge conflict resolver, unified patch applier with fuzz checks"),
    ("r15", "rule_linter", "heldout", "Python AST micro-linter: rule registry, scope/import tracker, inline `# noqa` suppression & diagnostic reporter"),
    ("r16", "rbac_policy", "heldout", "Policy-as-code RBAC/ABAC engine: role hierarchy graph, condition evaluator, explicit-deny conflict resolver"),
    ("r17", "order_match", "heldout", "Limit order matching engine: orderbook price-time queues, IOC/FOK/post-only execution rules, trade tape"),
    ("r18", "vfs_sandbox", "heldout", "In-memory POSIX virtual filesystem: inode/tree store, symlink & path normalizer, glob & quota operations"),
]

REPO_GUIDE_PROMPT = r"""You are a staff Python software engineer designing realistic multi-file debugging repositories for evaluating & RL-training coding agents (OpenCode / Pi with `glob`, `grep`, `read`, `edit`, `bash`/`pytest`).

================================================================================
1. REPOSITORY STRUCTURE & HARD VALIDATION GATES
================================================================================
Each task is a compact, realistic pure-Python 3.12 mini-repository (stdlib + pytest ONLY, zero third-party deps):
- Visible workspace (`WORK:` files seen by the agent):
  1. `TASK.md`: Realistic engineering issue report + exact behavioral specification (clear enough that an engineer reading TASK.md + code agrees 100% on every hidden test, WITHOUT pointing to exact buggy lines).
  2. `src/<pkg>/__init__.py`: Public package exports (re-export key classes/functions).
  3. 2 to 3 focused Python modules under `src/<pkg>/` (e.g. `models.py`, `parser.py`, `engine.py`, each ~35-70 lines, total ~110-190 lines) that genuinely import and call each other (`from <pkg>.models import ...`).
  4. `tests/test_smoke.py`: 2-3 basic visible pytest smoke tests (`from <pkg> import ...`) that PASS on the reference implementation (and may pass or partially fail on original) so the agent can run `pytest` via bash.
- Hidden grader (`HIDDEN:` + delta overlays `REF:` and `PARTIAL:`):
  5. `HIDDEN:tests_hidden/test_hidden.py`: 8 to 10 crisp, deterministic pytest test functions (`def test_...():`) covering happy paths AND every planted cross-module bug & edge case!
  6. `REF:<relpath>`: ONLY the 1-3 files under `src/<pkg>/` that change from `WORK:` to form the 100%-correct `reference` repo. (Unchanged files like `TASK.md` and `tests/test_smoke.py` are copied automatically from `WORK:`.)
  7. `PARTIAL:<relpath>`: ONLY the 1-2 files under `src/<pkg>/` that change from `WORK:` to form the `partial` repo (fixes Bug 1, leaves Bug 2 unfixed!).

HOW TO GUARANTEE ALL VALIDATION GATES PASS ON THE FIRST TRY:
- Import style: `pytest` runs with `PYTHONPATH=<repo>/src:<repo>`. ALWAYS use absolute package imports `from <pkg>.models import ...` (where `<pkg>` is a unique valid Python identifier like `miniorm`, `dagflow`, `httprouter`), NEVER relative imports in tests!
- Plant **2 independent cross-module bugs** in `WORK:` (e.g., Bug 1 in `src/<pkg>/parser.py` or `models.py`, Bug 2 in `src/<pkg>/engine.py` where modules interact):
  - 3-4 hidden tests exercise basic behavior -> PASS on `original`, `partial`, `reference`.
  - 2-3 hidden tests hit ONLY Bug 1 -> FAIL on `original`, PASS on `partial` and `reference`.
  - 2-3 hidden tests hit ONLY Bug 2 -> FAIL on `original` and `partial`, PASS on `reference`.
- NO `# BUG` or `# TODO` comments anywhere!
- Make sure `reference` passes 100% of BOTH `tests/test_smoke.py` AND `tests_hidden/test_hidden.py`!
- Never use wall-clock `time.time()` or randomness; pass explicit timestamps/seeds in inputs so tests are 100% deterministic.

================================================================================
2. EXACT DELIMITED OUTPUT FORMAT
================================================================================
Emit each repository task using these EXACT plain-text markers (do NOT wrap the whole output in JSON or outer markdown fences):

===REPO_TASK_START id="<batch>-<kebab-slug>"===
---WORK:TASK.md---
<issue report and complete spec>
---WORK:src/<pkg>/__init__.py---
<exports>
---WORK:src/<pkg>/models.py---
<module 1>
---WORK:src/<pkg>/engine.py---
<module 2>
---WORK:tests/test_smoke.py---
<2-3 visible pytest smoke tests>
---REF:src/<pkg>/models.py---
<fixed module 1>
---REF:src/<pkg>/engine.py---
<fixed module 2>
---PARTIAL:src/<pkg>/models.py---
<only Bug 1 fixed; Bug 2 remains in engine.py>
---HIDDEN:tests_hidden/test_hidden.py---
<8-10 deterministic hidden pytest tests>
===REPO_TASK_END===
"""

_TASK_RE = re.compile(r'===REPO_TASK_START\s+id="([^"]+)"\s*===(.*?)===REPO_TASK_END===', re.DOTALL)
_SEC_RE = re.compile(r"^---(WORK|REF|PARTIAL|HIDDEN):([^\r\n]+?)---\s*$", re.MULTILINE)


def _strip_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
    return s.rstrip() + "\n"


def _safe_rel(p: str) -> Path:
    rel = Path(p.strip().replace("\\", "/"))
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Unsafe relative path: {p}")
    return rel


def parse_repo_tasks(text: str) -> list[dict]:
    out = []
    for m in _TASK_RE.finditer(text):
        tid = m.group(1).strip()
        body = m.group(2)
        parts = _SEC_RE.split(body)
        sections: dict[str, dict[str, str]] = {"WORK": {}, "REF": {}, "PARTIAL": {}, "HIDDEN": {}}
        for i in range(1, len(parts) - 2, 3):
            kind, rel, content = parts[i], parts[i + 1].strip(), _strip_fence(parts[i + 2])
            sections[kind][rel] = content
        if "TASK.md" not in sections["WORK"] or not sections["HIDDEN"] or not sections["REF"]:
            continue
        out.append({"id": tid, **sections})
    return out


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.api_calls = 0
        self.disk_hits = 0
        self.prompt_toks = 0
        self.cached_toks = 0
        self.out_toks = 0

    def add(self, prompt_t=0, cached_t=0, out_t=0, disk=False):
        with self.lock:
            if disk:
                self.disk_hits += 1
            else:
                self.api_calls += 1
                self.prompt_toks += int(prompt_t or 0)
                self.cached_toks += int(cached_t or 0)
                self.out_toks += int(out_t or 0)

    def summary(self) -> str:
        with self.lock:
            return (f"calls={self.api_calls} disk={self.disk_hits} "
                    f"in={self.prompt_toks} cached={self.cached_toks} out={self.out_toks}")


def call_strong_model(key: str, session_id: str, messages: list[dict], stats: Stats,
                      model: str = "gemini-4-argon", fallback_model: str = "deepseek-v4.1-flash",
                      temperature: float = 0.35, max_tokens: int = 32768) -> tuple[str, bool]:
    """Call OpenCode Go strong model (Google v1beta or OpenAI route) with disk caching & strong-only fallback."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(
        json.dumps({"model": model, "messages": messages, "temperature": temperature}, sort_keys=True).encode()
    ).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.is_file():
        stats.add(disk=True)
        return json.loads(cache_file.read_text(encoding="utf-8"))["text"], False

    def _request_once(use_model: str):
        if use_model.startswith("gemini-"):
            contents = [
                {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in messages
            ]
            body = {
                "contents": contents,
                "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                                     "thinkingConfig": {"thinkingBudget": 512}},
            }
            url = GOOGLE_GO_URL.format(model=use_model)
            headers = {
                "Authorization": f"Bearer {key}", "x-goog-api-key": key,
                "Content-Type": "application/json", "User-Agent": "opencode/2.2.7",
                "x-opencode-client": "cli", "x-opencode-project": "proj_oca_repogen_v1",
                "x-opencode-session": session_id,
            }
            req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = json.loads(r.read().decode("utf-8"))
            cand = (raw.get("candidates") or [{}])[0]
            if cand.get("finishReason") == "MAX_TOKENS":
                raise RuntimeError(f"{use_model} truncated (MAX_TOKENS)")
            parts = (cand.get("content") or {}).get("parts") or []
            txt = "\n".join(p["text"] for p in parts if "text" in p and not p.get("thought")).strip()
            um = raw.get("usageMetadata") or {}
            stats.add(um.get("promptTokenCount", 0), um.get("cachedContentTokenCount", 0), um.get("candidatesTokenCount", 0))
            return txt
        else:
            body = {"model": use_model, "messages": messages, "temperature": temperature,
                    "max_tokens": max_tokens, "reasoning_effort": "low"}
            headers = {
                "Authorization": f"Bearer {key}", "Content-Type": "application/json",
                "User-Agent": "opencode/2.2.7", "x-opencode-client": "cli",
                "x-opencode-project": "proj_oca_repogen_v1", "x-opencode-session": session_id,
            }
            req = urllib.request.Request(OPENAI_GO_URL, data=json.dumps(body).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = json.loads(r.read().decode("utf-8"))
            ch = (raw.get("choices") or [{}])[0]
            if ch.get("finish_reason") == "length":
                raise RuntimeError(f"{use_model} truncated (length)")
            msg = ch.get("message") or {}
            txt = (msg.get("content") or "").strip()
            um = raw.get("usage") or {}
            pd = um.get("prompt_tokens_details") or {}
            stats.add(um.get("prompt_tokens", 0), pd.get("cached_tokens", 0), um.get("completion_tokens", 0))
            return txt

    models_try = [model, fallback_model, "qwen3.8-max"]
    last_err = None
    for m_idx, cur_model in enumerate(models_try):
        for attempt in range(3):
            try:
                txt = _request_once(cur_model)
                if not txt:
                    raise RuntimeError(f"empty response from {cur_model}")
                cache_file.write_text(json.dumps({"model": cur_model, "text": txt}, ensure_ascii=False), encoding="utf-8")
                return txt, True
            except urllib.error.HTTPError as e:
                err_b = e.read().decode("utf-8", errors="replace")[:300]
                last_err = f"{cur_model} HTTP {e.code}: {err_b}"
                if e.code == 429 and "GoUsageLimitError" in err_b:
                    break  # immediately rotate to next strong model
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(5 * (attempt + 1))
                    continue
                break
            except Exception as e:
                last_err = f"{cur_model} {e!r}"
                time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"All strong models failed: {last_err}")


def materialize_repo_task(out_base: Path, item: dict, prefix: str) -> tuple[str, dict]:
    raw_id = re.sub(r"[^a-z0-9-]+", "-", item["id"].lower()).strip("-")
    if not raw_id.startswith(prefix + "-"):
        raw_id = f"{prefix}-{raw_id or 'repo'}"
    tdir = out_base / "tasks" / raw_id
    gdir = out_base / "grader" / raw_id
    shutil.rmtree(tdir, ignore_errors=True)
    shutil.rmtree(gdir, ignore_errors=True)

    # 1. Write WORK files
    for rel_s, content in item["WORK"].items():
        fp = tdir / _safe_rel(rel_s)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")

    # 2. Materialize REF & PARTIAL by cloning WORK and overlaying diffs
    for variant, key in (("reference", "REF"), ("partial", "PARTIAL")):
        vdir = gdir / variant
        shutil.copytree(tdir, vdir)
        for rel_s, content in item[key].items():
            fp = vdir / _safe_rel(rel_s)
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(content, encoding="utf-8")

    # 3. Write HIDDEN tests under grader/<id>/tests_hidden/
    for rel_s, content in item["HIDDEN"].items():
        rel = _safe_rel(rel_s)
        if not rel.parts or rel.parts[0] != "tests_hidden":
            rel = Path("tests_hidden") / rel.name
        fp = gdir / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")

    verdict = check_repo_task(tdir, gdir, require_partial=True)
    return raw_id, verdict


def run_worker(worker_idx: int, key: str, specs: list[tuple[str, str, str, str]],
               out_base: Path, tasks_per_domain: int, model: str, fallback: str, stats: Stats) -> list[dict]:
    session_id = f"ses_oca_repogen_k{worker_idx}_v1"
    prefix_msgs = [
        {"role": "user", "content": REPO_GUIDE_PROMPT},
        {"role": "assistant", "content": "Understood. Send the domain spec and I will emit complete multi-file repo_pytest tasks using exact ===REPO_TASK_START=== / ---WORK:...--- / ---REF:...--- / ---PARTIAL:...--- / ---HIDDEN:...--- markers."},
    ]
    accepted = []

    for bid, domain, split, desc in specs:
        for slot in range(1, tasks_per_domain + 1):
            slot_prefix = f"{bid}s{slot}"
            existing = [p for p in (out_base / "tasks").glob(f"{slot_prefix}-*") if p.is_dir()] if (out_base / "tasks").is_dir() else []
            if existing:
                tid = existing[0].name
                res = check_repo_task(out_base / "tasks" / tid, out_base / "grader" / tid)
                if res["ok"]:
                    accepted.append({"id": tid, "split": split, "domain": domain, "kind": "repo_pytest",
                                     "src_modules": res["src_modules"], "passed": res["passed"]})
                    print(f"[k{worker_idx}:{slot_prefix}] cached valid {tid}", flush=True)
                    continue

            angle = (
                "Focus on cross-module data parsing/validation interacting with stateful execution."
                if slot % 2 == 1
                else "Focus on edge-case conflict resolution, rollback/invalidation, and multi-step query composition."
            )
            prompt = (
                f"Task ID prefix: `{slot_prefix}` (use a unique short Python package name under `src/` such as `{slot_prefix}pkg`).\n"
                f"Domain ({domain}): {desc}\n"
                f"Design angle #{slot}: {angle}\n\n"
                f"Author 1 distinct, realistic multi-file Python 3.12 mini-repository (`src/<pkg>/__init__.py` + 2-3 cohesive modules "
                f"+ `tests/test_smoke.py` + `TASK.md` + `REF:` + `PARTIAL:` + `HIDDEN:tests_hidden/test_hidden.py` with 8-10 pytest tests).\n"
                f"Ensure 2 independent realistic cross-module bugs in WORK, PARTIAL fixes Bug 1 only, REF passes 100% of visible & hidden pytest."
            )
            msgs = [*prefix_msgs, {"role": "user", "content": prompt}]
            t0 = time.time()
            try:
                text, _ = call_strong_model(key, session_id, msgs, stats, model=model, fallback_model=fallback)
                items = parse_repo_tasks(text)
                if not items:
                    raise ValueError("no ===REPO_TASK_START=== block parsed")
            except Exception as e:
                print(f"[k{worker_idx}:{slot_prefix}] gen error: {e}", flush=True)
                continue

            item = items[0]
            try:
                tid, res = materialize_repo_task(out_base, item, slot_prefix)
            except Exception as e:
                tid, res = f"{slot_prefix}-err", {"ok": False, "problems": [repr(e)]}

            if not res["ok"]:
                # 1-turn cached self-repair
                repair_msgs = [
                    *msgs,
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": (
                        f"Your task `{tid}` failed `oca.validate.check_repo_task`:\n"
                        f"{res['problems']}\n\n"
                        f"Emit ONLY the single corrected `===REPO_TASK_START id=\"{tid}\"=== ... ===REPO_TASK_END===` block "
                        f"fixing every problem above."
                    )},
                ]
                try:
                    rtext, _ = call_strong_model(key, session_id, repair_msgs, stats, model=model,
                                                 fallback_model=fallback, temperature=0.2)
                    ritems = parse_repo_tasks(rtext)
                    if ritems:
                        tid, res = materialize_repo_task(out_base, ritems[0], slot_prefix)
                except Exception as e:
                    print(f"[k{worker_idx}:{slot_prefix}] repair error: {e}", flush=True)

            if res["ok"]:
                row = {"id": tid, "split": split, "domain": domain, "kind": "repo_pytest",
                       "src_modules": res["src_modules"], "passed": res["passed"]}
                accepted.append(row)
                print(f"[k{worker_idx}:{slot_prefix}] OK {tid} ({res['src_modules']} mods, {res['passed']}) "
                      f"in {time.time()-t0:.1f}s | {stats.summary()}", flush=True)
            else:
                shutil.rmtree(out_base / "tasks" / tid, ignore_errors=True)
                shutil.rmtree(out_base / "grader" / tid, ignore_errors=True)
                print(f"[k{worker_idx}:{slot_prefix}] FAIL {tid}: {res['problems'][:2]}", flush=True)

    return accepted


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keys-file", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data" / "repo_v1")
    ap.add_argument("--tasks-per-domain", type=int, default=3)
    ap.add_argument("--limit-domains", type=int, default=0)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--model", default="gemini-4-argon")
    ap.add_argument("--fallback-model", default="deepseek-v4.1-flash")
    args = ap.parse_args()

    keys = [l.strip() for l in args.keys_file.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    if not keys:
        raise SystemExit("No keys found")

    specs = REPO_DOMAINS[:args.limit_domains] if args.limit_domains > 0 else REPO_DOMAINS
    n_workers = min(max(1, args.workers), len(specs))
    shards = [[] for _ in range(n_workers)]
    for i, sp in enumerate(specs):
        shards[i % n_workers].append(sp)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stats = Stats()
    t0 = time.time()
    rows = []
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futs = [
            pool.submit(run_worker, wi, keys[wi % len(keys)], shards[wi], args.out_dir,
                        args.tasks_per_domain, args.model, args.fallback_model, stats)
            for wi in range(n_workers) if shards[wi]
        ]
        for f in as_completed(futs):
            rows.extend(f.result())

    # Merge with any previously valid rows in manifest (idempotent reruns)
    mpath = args.out_dir / "manifest.json"
    existing_by_id = {}
    if mpath.is_file():
        for r in json.loads(mpath.read_text(encoding="utf-8")).get("tasks") or []:
            if (args.out_dir / "tasks" / r["id"]).is_dir() and (args.out_dir / "grader" / r["id"]).is_dir():
                existing_by_id[r["id"]] = r
    for r in rows:
        existing_by_id[r["id"]] = r
    final_rows = sorted(existing_by_id.values(), key=lambda x: x["id"])

    # Verify strict domain disjointness
    tr_d = {r["domain"] for r in final_rows if r["split"] == "train"}
    ho_d = {r["domain"] for r in final_rows if r["split"] == "heldout"}
    assert not (tr_d & ho_d), f"Domain leakage: {tr_d & ho_d}"

    mpath.write_text(json.dumps({"tasks": final_rows}, indent=2) + "\n", encoding="utf-8")
    summary = {
        "total_valid": len(final_rows),
        "splits": dict(Counter(r["split"] for r in final_rows)),
        "train_domains": sorted(tr_d),
        "heldout_domains": sorted(ho_d),
        "elapsed_s": round(time.time() - t0, 1),
        "usage": stats.summary(),
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\n=== REPO_PYTEST GENERATION COMPLETE ===", flush=True)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
