"""Cached multi-key task synthesis & automatic verification using OpenCode Go (`gemini-4-argon`).

Design highlights for maximum prompt-cache & disk-cache efficiency:
1. Native Google v1beta route (`https://opencode.ai/inference/go/google/v1beta/models/gemini-4-argon:generateContent`)
   with a deterministic >=5,000-token `contents[0..1]` prefix and per-key sticky `x-opencode-session`.
2. Per-key 6.5s warmup after the first request so Gemini indexes the implicit cache (`cache_read` ~20x cheaper
   than uncached input), followed by sequential batches per key across 5 keys in parallel.
3. Multi-turn self-repair for any task failing `oca.validate` (appends turn 3/4 so the draft itself hits cache).
4. Local SHA-256 response cache in `.cache/argon/` (gitignored) so reruns cost zero API calls.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
import urllib.error
import urllib.request

from . import ROOT
from .validate import check_task

ENDPOINT = "https://opencode.ai/inference/go/google/v1beta/models/gemini-4-argon:generateContent"
OPENAI_GO_ENDPOINT = "https://opencode.ai/inference/go/openai/v1/chat/completions"
CACHE_DIR = ROOT / ".cache" / "argon"
_FALLBACK_FREE = False

# 20 distinct standard-library algorithmic & systems domains (2 batches x 5 tasks = 200 candidate tasks)
BATCH_SPECS = [
    ("d01a", "CSV/TSV & custom delimiter dialects: quoted newlines, escaped quotes, comment lines, header normalization, type coercion"),
    ("d01b", "INI / TOML-lite / dotenv config parsers: section inheritance, inline comments, multiline quotes, variable expansion with cycle error"),
    ("d02a", "Shell & query-string tokenizers: POSIX-like quoting/escaping, brace expansion, URL query nested bracket keys, filter DSL lexer"),
    ("d02b", "Markdown & markup mini-parsers: inline emphasis/code spans, table cell splitting with escaped pipes, heading slugifier with dedup, footnote numbering"),
    ("d03a", "Calendar & business-day scheduling: holiday-aware business day offset, end-of-month clamping recurrences, ISO week date conversion, SLA deadline calculator"),
    ("d03b", "Interval & booking engines: room allocation min-rooms/assignment, merge/subtract half-open intervals, blackout-window clipping, recurring slot conflict detector"),
    ("d04a", "Stateful caches via `run(ops)` driver: LRU with TTL expiry, LFU cache with recency tie-break, write-back buffer with flush, sliding-window counter"),
    ("d04b", "Stateful containers via `run(ops)` driver: undo/redo text buffer, indexed min-heap with decrease_key/delete, transactional KV store with nested begin/commit/rollback, bounded deque ring"),
    ("d05a", "Exact decimal & money arithmetic: split cents with remainder fairness, banker's vs half-up rounding on decimal strings, progressive tiered fee/tax, currency ledger FX conversion using rational ints"),
    ("d05b", "Number theory & checksums: arbitrary base (-36..36 or 2..62) rational/int conversion, Luhn/ISBN-13/IBAN check digits, continued-fraction rational approximation, Chinese remainder solver"),
    ("d06a", "Deterministic graph algorithms: lexicographic Kahn topo-sort with cycle node reporting, Dijkstra shortest path with fewest-hops tie-break, Tarjan SCC condensation, bipartite two-coloring"),
    ("d06b", "Dependency & constraint solvers: semver-lite package resolver with conflict pin reporting, task critical-path earliest/latest finish, union-find with weighted relative offsets, course prereq planner"),
    ("d07a", "Text layout & fixed-width formatting: ASCII box table with column alignment/wrapping, paragraph justified/hyphen-free word-wrap with hanging indent, tree pretty-printer, unified diff hunk formatter"),
    ("d07b", "Human-friendly formatting & parsing: IEC/SI byte units parser+formatter, compound duration ('2d 3h 04m') canonicalizer, English plural/ordinal inflector, locale number grouping"),
    ("d08a", "Iterator & sequence combinators: windowed aggregation with step/fill, k-way sorted merge with key spec & dedup policy, run-length segmenter, stable multi-key group-by rollup"),
    ("d08b", "Tree & nested JSON transforms: JSON Pointer (RFC 6901) get/set/remove, deep dict merge with list strategies, path-globbing flattener/unflattener, mini JSON-schema validator returning sorted error paths"),
    ("d09a", "Diff, edit distance & patching: Myers/LCS line diff hunks, unified hunk applier with context verification, Damerau-Levenshtein distance, 3-way line merge with conflict markers"),
    ("d09b", "Mini interpreters & evaluators: Pratt/shunting-yard arithmetic with unary ops/variables/errors, stack bytecode VM with jumps/calls, glob matcher with `**` and `[!a-z]`, tiny Mustache-like template renderer"),
    ("d10a", "Backend systems logic via `run(ops)`: token-bucket & leaky-bucket rate limiter, inventory reservation with expiration, cursor-based pagination encoder/slicer, job retry backoff state machine"),
    ("d10b", "Binary/text encodings: varint & zigzag encode/decode on byte lists, RFC 4648 base32/base32hex without padding bugs, UTF-8 percent-encoding/decoding, strict Roman numeral converter (1..3999) + bitfield packer"),
    ("d11a", "Log & metrics analytics: sliding-percentile/histogram aggregator, sessionization with idle-gap split, structured key=val log parser with quotes, anomaly streak detector"),
    ("d11b", "Routing & permissions: URL path-template router with wildcard/param priority, RBAC/glob policy matcher with deny-overrides, CIDR IPv4 subnet containment & coalescing, feature-flag rollout evaluator"),
    ("d12a", "Grid & 2D simulation: Conway/cellular step with toroidal/bounded modes, robot path simulator with obstacles & turn commands, connected-region flood labeler, sparse matrixCSR multiply/transpose"),
    ("d12b", "String search & compression: Aho-Corasick / multi-pattern non-overlapping replacer, LZ77/RLE token stream codec, camel/snake/kebab identifier converter preserving acronyms ('HTTPResponseCode'), BWT/MTF transform"),
    ("d13a", "Financial & auction matching: price-time priority limit order book via `run(ops)`, FIFO/LIFO cost-basis capital gains calculator, split-expense minimum-cash-flow settler, Dutch/Vickrey auction clearing"),
    ("d13b", "Compiler/AST passes on JSON trees: constant folding & dead-branch pruning on expression ASTs, variable shadowing/renaming alpha-converter, topological formula spreadsheet evaluator with `#CYCLE!` detection, regex-subset NFA matcher"),
    ("d14a", "Testing & data-quality utilities: table primary-key/foreign-key violation checker, deterministic reservoir/stratified index selector (pure formula), cron-field set expander ('*/15,2-5'), Myers sequence alignment"),
    ("d14b", "Protocol framing & state machines: length-prefixed frame reassembler across chunks via `run(ops)`, HTTP-like header folding/canonicalizer, circuit-breaker half-open state machine, hierarchical statechart transition runner"),
    ("d15a", "String & identifier algorithms: natural human sort key ('file2' < 'file10'), wildcard route globbing, balanced bracket/tag repairer, longest non-overlapping repeating substring"),
    ("d15b", "Time-series & event windows: session watermark late-event aggregator via `run(ops)`, exponential moving integer-scaled smoother, gap-filling forward/linear interpolator on int grids, OHLC bar builder"),
    ("d16a", "Set & interval algebra: disjoint integer range set (`add`/`remove`/`query` via `run(ops)`), 2D axis-aligned rectangle union area, skyline contour builder, k-core graph peeling"),
    ("d16b", "Security-free access & quota engines: hierarchical quota tree (`org/team/user`) via `run(ops)`, weighted fair queueing packet scheduler, consistent-hash ring virtual-node router, lease lock manager with fencing tokens"),
    ("d17a", "Structured document & table transforms: pivot/unpivot table aggregator with missing-cell fill, CSV schema inference (int/bool/date/str), markdown outline numbering, nested list indentation parser"),
    ("d17b", "Combinatorial & discrete math: next/k-th lexicographic permutation with duplicates, balanced partition / subset-sum tie-breaker, polynomial exact arithmetic over rationals, sparse polynomial evaluator"),
    ("d18a", "Filesystem-path & archive models (in-memory): POSIX path normalizer with symlink resolution & loop error, gitignore-subset matcher, virtual in-memory tar/dir tree `du`/`mv`/`cp` via `run(ops)`"),
    ("d18b", "Workflow & build-graph engines: incremental build invalidation tracker via `run(ops)`, retryable DAG task runner simulation, topological config override resolver, changelog semver bump calculator"),
    ("d19a", "Game & turn-based rule engines: deterministic Elo/Glicko-lite integer rating updater, Minesweeper flood-reveal & flag validator, Tetris/falling-block column height simulator, poker 5-card hand comparator"),
    ("d19b", "Query & index structures: inverted index boolean/phrase search (`AND`/`OR`/`NOT`/quotes), prefix trie autocomplete with frequency+lexicographic top-k via `run(ops)`, B-tree/skip-list range scan"),
    ("d20a", "Data serialization & wire codecs: RESP (Redis protocol) encoder/decoder, netstring/bencode parser & canonical serializer with error reporting, TLV binary record stream parser"),
    ("d20b", "Resource & batch schedulers: bin-packing first-fit/best-fit decreasing with item affinities, CPU round-robin/EDF process scheduler simulator, sliding-window SLA violation tracker, multi-stage pipelinelatency simulator"),
]

SHARED_GUIDE_PROMPT = r"""You are a principal Python benchmark designer authoring RL coding environments for Qwen3-8B inside the OpenCode CLI (`read`, `edit`, `write`, `shell` tools).
Read every contract, edge-case rule, and reference example carefully. Every task you emit will be executed immediately by an automated hidden test harness; any ambiguity or violated invariant will fail validation.

================================================================================
1. EXACT EXECUTION & GRADING CONTRACT
================================================================================
The coding agent ONLY sees two files in its working directory:
  - `TASK.md`: The complete natural-language specification.
  - `solution.py`: A realistic, buggy Python 3.12 module (45 to 135 lines).

The hidden grader (`oca/grade.py`) runs `solution.py` in an isolated Python 3.12 subprocess with NO network, NO filesystem expectations, and executes this exact worker:
```python
import contextlib, json, runpy, sys
def decode(v):
    if isinstance(v, list): return [decode(i) for i in v]
    if isinstance(v, dict):
        if set(v) == {"$float"}: return float(v["$float"])
        return {k: decode(i) for k, i in v.items()}
    return v
req = json.load(sys.stdin)
out = []
with contextlib.redirect_stdout(sys.stderr):
    fn = runpy.run_path(sys.argv[1])[req["function"]]
    for args in req["inputs"]:
        try: out.append({"value": fn(*decode(args))})
        except Exception as e: out.append({"raises": type(e).__name__})
print(json.dumps(out, ensure_ascii=True, allow_nan=False))
```
Then for each case in `cases.json`, the grader checks:
```python
expected = {k: case[k] for k in ("raises", "value") if k in case}
ok = json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)
```

CRITICAL IMPLICATIONS OF THIS GRADER:
1. JSON TYPES ONLY:
   - In Python, returning a `tuple` `(1, 2)` serializes via `json.dumps` to `[1, 2]`. Therefore in `cases.json`, `"value"` MUST ALWAYS use JSON arrays `[...]`, NEVER Python tuples, sets, or non-string dict keys!
   - NEVER return `float('nan')` or `float('inf')` (`allow_nan=False` will crash). Avoid floating-point return values altogether! Return exact `int`, `str` (e.g. `"12.34"`), `bool`, `None`, `list`, or `dict` with `str` keys.
   - All `args` in `cases.json` is a positional argument list `[arg1, arg2, ...]` unpacked as `fn(*args)`. Even if `fn` takes 1 list argument `ops`, `args` MUST be `[ops]` (a outer list wrapping the positional args)! Double-check this!
2. EXCEPTIONS:
   - Expected exceptions use `{"id": "bad_input", "args": [...], "raises": "ValueError"}` (do NOT include `"value"` when `"raises"` is used). Only check standard built-in exception class names (`"ValueError"`, `"KeyError"`, `"TypeError"`, `"IndexError"`, `"ZeroDivisionError"`).
3. AUTOMATED VALIDATOR (`oca/validate.py`) HARD GATES — ALL MUST HOLD:
   - Gate A: `TASK.md` MUST contain the exact graded function name preceded by an opening backtick, e.g. `` `solve_schedule(events, limit)` `` or `` `run(ops)` ``.
   - Gate B: `len(cases) >= 8` (aim for 9 to 12 diverse cases) and all `case["id"]` strings are unique within the task.
   - Gate C (`reference.py`): MUST pass **100%** of `cases` (`passed == total`).
   - Gate D (`solution.py`, the buggy starting code): MUST fail overall (`passed < total`), AND should pass at least 1-4 basic happy-path cases so it looks like genuine buggy production code rather than a stub.
   - Gate E (`partial.py`, an incomplete fix): MUST fail overall (`passed < total`), AND MUST pass **strictly more** cases than `solution.py`: `0 <= passed(solution.py) < passed(partial.py) < passed(reference.py) == total`!
     How to guarantee Gate E effortlessly:
     Give `solution.py` **2 or 3 independent bugs** (Bug 1, Bug 2, [Bug 3]), each tested by dedicated cases in `cases.json` that do NOT hit the other bugs! Then construct `partial.py` by starting from `reference.py` and re-introducing ONLY Bug 2 (while keeping Bug 1 fixed)! That mathematically guarantees `passed(solution) < passed(partial) < total`!

================================================================================
2. CALIBRATING DIFFICULTY FOR RL (TARGET: 20%-75% BASE PASS RATE ON QWEN3-8B)
================================================================================
Why existing v3 tasks were too easy: they were 6-line functions with 1 obvious typo, so Qwen3-8B solved >90% on attempt 1 (zero GRPO variance!).
To hit the sweet spot where Qwen3-8B solves SOME rollouts (when it reads carefully and runs `python3` via `shell` to test edge cases) and FAILS others (when it guesses hastily):
- Make `solution.py` **50 to 130 lines** with 2–4 helper functions or a clean stateful class + top-level driver function (such as `run(ops: list[dict]) -> list`).
- Plant **2 or 3 subtle, realistic, unmarked bugs** (NO `# BUG` or `# TODO` comments!):
  * Off-by-one boundary (`<` vs `<=`, slice end, empty window, last flush after loop ends)
  * Wrong tie-breaking order or unstable sort / mutating caller's input list across steps
  * State leakage across resets/rollbacks/expirations (e.g. forgetting to evict expired keys before checking capacity, or forgetting to update secondary index on overwrite)
  * Precedence / sign / negative-modulo / escaping edge case (e.g. `\\"` before closing quote, trailing empty field, `0` falsiness treated as `None` via `x or default` instead of `default if x is None else x`!)
- Make `TASK.md` **100% fair, complete, and crystal clear**:
  * Explicitly document the function signature, parameter types, exact return structure, tie-breaking rules, boundary/empty behaviors, and exact exception types to raise on invalid inputs.
  * Include 1–2 small concrete input/output examples in `TASK.md` (do NOT leak all hidden test cases or state where the bugs are).
  * A careful human engineer reading ONLY `TASK.md` and `reference.py` must agree 100% on every single case in `cases.json`. Never invent an undocumented rule in `cases.json`!

================================================================================
3. WORKED GOLD EXAMPLES (MATCH THIS EXACT QUALITY & JSON SCHEMA)
================================================================================

--- Gold Example 1: Stateful `run(ops)` Task ---
- `id`: `"ex-ttl-lru"`
- `bugs`: 2
- `TASK.md`:
  "Fix `run_cache(capacity, ops)` in `solution.py`.\n\nImplement a deterministic TTL-aware LRU cache driven by integer timestamps.\n- `capacity`: positive integer (`>= 1`); raise `ValueError` if `capacity < 1`.\n- `ops`: list of operation dicts processed in non-decreasing `t` (integer timestamp) order:\n  1. `{\"op\": \"put\", \"t\": int, \"key\": str, \"val\": int, \"ttl\": int | None}`: First purge all entries whose `expire_at <= t`. If `ttl is not None` and `ttl <= 0`, do not store the key (and if `key` already existed, remove it) and append `None` to results. Otherwise insert/update `key` with value `val` and expiration `None if ttl is None else t + ttl`, mark `key` as most-recently-used, evicting the least-recently-used remaining entry if adding a new key would exceed `capacity`. Append `None`.\n  2. `{\"op\": \"get\", \"t\": int, \"key\": str}`: First purge all entries with `expire_at <= t`. If `key` is present, mark it most-recently-used and append its integer value; otherwise append `-1`.\n  3. `{\"op\": \"keys\", \"t\": int}`: Purge all entries with `expire_at <= t` without changing recency order, and append the list of remaining keys ordered from least-recently-used to most-recently-used.\n\nExample:\n`run_cache(2, [{\"op\": \"put\", \"t\": 0, \"key\": \"a\", \"val\": 10, \"ttl\": 5}, {\"op\": \"get\", \"t\": 3, \"key\": \"a\"}, {\"op\": \"get\", \"t\": 5, \"key\": \"a\"}])` returns `[None, 10, -1]`."
- Design of the 3 code variants:
  * `reference.py`: Uses ` collections.OrderedDict`, purges `expire_at is not None and expire_at <= t` before every op, handles `ttl == 0` by popping existing key and returning, uses `val` even when `val == 0`, evicts only after purging expired items.
  * `partial.py`: Fixes eviction-after-purge and recency update on `get`, STILL has 1 bug: checks `if ttl:` instead of `if ttl is not None:`, so `ttl=0` is treated like `ttl=None` (immortal)!
  * `solution.py`: Has BOTH the `if ttl:` bug AND evicts LRU *before* purging expired entries on `put` (so an expired entry causes a live entry to be evicted when at capacity)!
  * `cases.json`: `"function": "run_cache"`, 9 cases where `"args": [capacity, ops]`:
    - 3 basic LRU/TTL cases pass on all three (`solution`, `partial`, `reference`)
    - 3 capacity-with-expired-item cases fail on `solution`, pass on `partial` and `reference`
    - 3 `ttl=0` / negative `ttl` / `capacity=0` cases fail on `solution` and `partial`, pass on `reference`!

--- Gold Example 2: Algorithmic / Parser Task ---
- `id`: `"ex-kv-interp"`
- `bugs`: 3
- `TASK.md` specifies `parse_env(text)` parsing `KEY=VALUE` lines with `#` comments (only outside quotes), single quotes (literal), double quotes (`\"`, `\\`, `\n` escapes + `${VAR}` interpolation against already-defined keys or `""` if undefined, raising `ValueError` on unclosed quotes or invalid identifier keys).
- `reference.py` implements clean character-by-character scanning (~85 lines).
- `partial.py` fixes escaped quotes and inline `#` inside quotes, but leaves `${VAR}` expanding inside single-quoted strings.
- `solution.py` has both `${VAR}` inside single quotes AND splits on `#` naively before quote parsing!

================================================================================
4. EXACT DELIMITED OUTPUT FORMAT FOR EACH BATCH CALL
================================================================================
Do NOT wrap the whole response in JSON (putting Python code inside JSON strings causes quote-escaping bugs).
Instead, emit each task using these EXACT plain-text markers:

===TASK_START id="<batch_prefix>-<kebab-slug>" bugs="2"===
---FILE:TASK.md---
<exact contents of TASK.md; must include `<function_name>(...)` in backticks>
---FILE:solution.py---
<exact contents of buggy solution.py, 50-85 lines, pure Python 3.12 stdlib, NO comments marking bugs>
---FILE:partial.py---
<exact contents of incomplete-fix partial.py: fixes >=1 bug from solution.py, leaves >=1 bug unfixed>
---FILE:reference.py---
<exact contents of 100%-correct reference.py>
---FILE:cases.json---
{"function": "<exact_top_level_function_name>", "cases": [
  {"id": "basic_1", "args": [...], "value": ...},
  {"id": "error_1", "args": [...], "raises": "ValueError"}
]}
===TASK_END===

Double-check your mental execution of EVERY case in `cases.json` against `reference.py`, `partial.py`, and `solution.py` before outputting! Ensure:
1. `reference.py` produces the EXACT `value` (as JSON lists, never tuples/floats) or `raises` for every single case.
2. `partial.py` passes strictly more cases than `solution.py` and fails at least 1 case (`passed(solution) < passed(partial) < total`).
3. `solution.py` passes at least 1 case and fails at least 2 cases (`len(cases) >= 8`).
4. `TASK.md` names `` `<function>(...)` `` in backticks and specifies every edge case tested.
"""


class UsageTracker:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = 0
        self.disk_hits = 0
        self.input_tokens = 0
        self.cache_read_tokens = 0
        self.output_tokens = 0
        self.allowance = 0.0

    def add_api(self, usage_meta: dict):
        oc = (usage_meta or {}).get("opencode") or {}
        toks = oc.get("tokens") or {}
        with self.lock:
            self.calls += 1
            self.input_tokens += int(toks.get("input") or 0)
            self.cache_read_tokens += int(toks.get("cache_read") or usage_meta.get("cachedContentTokenCount") or 0)
            self.output_tokens += int(toks.get("output") or usage_meta.get("candidatesTokenCount") or 0)
            self.allowance += float(oc.get("allowance") or 0.0)

    def add_disk_hit(self):
        with self.lock:
            self.disk_hits += 1

    def summary(self) -> str:
        with self.lock:
            total_prompt = self.input_tokens + self.cache_read_tokens
            hit_pct = (100.0 * self.cache_read_tokens / total_prompt) if total_prompt else 0.0
            return (f"api_calls={self.calls} disk_hits={self.disk_hits} "
                    f"uncached_in={self.input_tokens} cache_read={self.cache_read_tokens} "
                    f"({hit_pct:.1f}% cached) out={self.output_tokens} allowance=${self.allowance:.4f}")


_TASK_RE = re.compile(
    r'===TASK_START\s+id="([^"]+)"(?:\s+bugs="(\d+)")?\s*===(.*?)===TASK_END===',
    re.DOTALL,
)
_FILE_SPLIT_RE = re.compile(r"^---FILE:(TASK\.md|solution\.py|partial\.py|reference\.py|cases\.json)---\s*$", re.MULTILINE)


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", s)
        s = re.sub(r"\n?```\s*$", "", s)
    return s.strip()


def parse_delimited_tasks(text: str) -> list[dict]:
    out = []
    for m in _TASK_RE.finditer(text):
        tid, bugs_s, body = m.group(1).strip(), m.group(2), m.group(3)
        parts = _FILE_SPLIT_RE.split(body)
        files = {}
        for i in range(1, len(parts) - 1, 2):
            files[parts[i]] = _strip_code_fence(parts[i + 1])
        req_files = ("TASK.md", "solution.py", "partial.py", "reference.py", "cases.json")
        if not all(k in files for k in req_files):
            continue
        try:
            cases_obj = json.loads(files["cases.json"])
        except json.JSONDecodeError:
            # Fallback locate outermost {...}
            raw_c = files["cases.json"]
            st, en = raw_c.find("{"), raw_c.rfind("}")
            if st == -1 or en <= st:
                continue
            try:
                cases_obj = json.loads(raw_c[st:en + 1])
            except json.JSONDecodeError:
                continue
        out.append({
            "id": tid,
            "bugs": int(bugs_s) if bugs_s else 2,
            "task_md": files["TASK.md"],
            "solution_py": files["solution.py"],
            "partial_py": files["partial.py"],
            "reference_py": files["reference.py"],
            "cases_json": cases_obj,
        })
    return out


def _call_openai_go_free(key: str, session_id: str, contents: list[dict], tracker: UsageTracker,
                         model: str, temperature: float, max_output_tokens: int) -> tuple[str, bool]:
    msgs = [
        {"role": "assistant" if c["role"] == "model" else "user",
         "content": "\n".join(p.get("text", "") for p in c.get("parts", []))}
        for c in contents
    ]
    body = {"model": model, "messages": msgs, "temperature": temperature, "max_tokens": max_output_tokens}
    cache_key = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.is_file():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        tracker.add_disk_hit()
        return cached["text"], False

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "opencode/2.2.7",
        "x-opencode-client": "cli",
        "x-opencode-project": "proj_oca_taskgen_v1",
        "x-opencode-session": session_id,
    }
    payload = json.dumps(body).encode("utf-8")
    last_err = None
    for attempt in range(4):
        req = urllib.request.Request(OPENAI_GO_ENDPOINT, data=payload, headers=headers, method="POST")
        try:
            print(f"  -> POST {model} ({session_id}, attempt {attempt+1})...", flush=True)
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            msg = (raw.get("choices") or [{}])[0].get("message") or {}
            text = (msg.get("content") or "").strip()
            if not text:
                raise RuntimeError(f"empty text from {model}: {str(raw)[:300]}")
            usage = raw.get("usage") or {}
            tracker.add_api(usage)
            cache_file.write_text(json.dumps({"text": text, "usage": usage}, ensure_ascii=False), encoding="utf-8")
            return text, True
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            last_err = f"HTTP {e.code}: {err_body}"
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(6 * (attempt + 1))
                continue
            raise RuntimeError(last_err) from None
        except Exception as e:
            last_err = repr(e)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"{model} failed after retries: {last_err}")


def call_argon(key: str, session_id: str, contents: list[dict], tracker: UsageTracker,
               temperature: float = 0.4, max_output_tokens: int = 32768,
               model: str = "gemini-4-argon") -> tuple[str, bool]:
    """Call gemini-4-argon (or auto-fallback to OpenCode Go free model on 5h quota cap) with SHA-256 disk caching."""
    global _FALLBACK_FREE
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if model != "gemini-4-argon" or _FALLBACK_FREE:
        eff_model = "hy4-flash-free" if model == "gemini-4-argon" else model
        return _call_openai_go_free(key, session_id, contents, tracker, eff_model, temperature, max_output_tokens)

    body = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
            "thinkingConfig": {"thinkingBudget": 256},
        },
    }
    cache_key = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.is_file():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        tracker.add_disk_hit()
        return cached["text"], False

    headers = {
        "Authorization": f"Bearer {key}",
        "x-goog-api-key": key,
        "Content-Type": "application/json",
        "User-Agent": "opencode/2.2.7",
        "x-opencode-client": "cli",
        "x-opencode-project": "proj_oca_taskgen_v1",
        "x-opencode-session": session_id,
    }
    payload = json.dumps(body).encode("utf-8")
    last_err = None
    for attempt in range(4):
        req = urllib.request.Request(ENDPOINT, data=payload, headers=headers, method="POST")
        try:
            print(f"  -> POST argon ({session_id}, attempt {attempt+1})...", flush=True)
            with urllib.request.urlopen(req, timeout=150) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
            parts = (((raw.get("candidates") or [{}])[0].get("content") or {}).get("parts")) or []
            text_parts = [p["text"] for p in parts if "text" in p and not p.get("thought")]
            if not text_parts:
                text_parts = [p["text"] for p in parts if "text" in p]
            text = "\n".join(text_parts)
            if not text.strip():
                raise RuntimeError(f"empty text from argon: {str(raw)[:300]}")
            usage = raw.get("usageMetadata") or {}
            tracker.add_api(usage)
            cache_file.write_text(json.dumps({"text": text, "usage": usage}, ensure_ascii=False), encoding="utf-8")
            return text, True
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")[:500]
            last_err = f"HTTP {e.code}: {err_body}"
            if e.code == 429 and "GoUsageLimitError" in err_body:
                _FALLBACK_FREE = True
                print("  [quota] Paid Go 5h allowance full; auto-switching to OpenCode Go `hy4-flash-free` ($0)", flush=True)
                return _call_openai_go_free(key, session_id, contents, tracker, "hy4-flash-free",
                                            temperature, max_output_tokens)
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(8 * (attempt + 1))
                continue
            raise RuntimeError(last_err) from None
        except Exception as e:
            last_err = repr(e)
            time.sleep(6 * (attempt + 1))
    raise RuntimeError(f"argon failed after retries: {last_err}")


def materialize_and_check(out_base: Path, item: dict, expected_prefix: str) -> tuple[str, dict]:
    raw_id = str(item.get("id") or "").strip().lower()
    raw_id = re.sub(r"[^a-z0-9-]+", "-", raw_id).strip("-")
    if not raw_id.startswith(expected_prefix + "-"):
        raw_id = f"{expected_prefix}-{raw_id or 'task'}"
    tdir = out_base / "tasks" / raw_id
    gdir = out_base / "grader" / raw_id
    shutil.rmtree(tdir, ignore_errors=True)
    shutil.rmtree(gdir, ignore_errors=True)
    tdir.mkdir(parents=True, exist_ok=True)
    gdir.mkdir(parents=True, exist_ok=True)
    (tdir / "TASK.md").write_text(str(item["task_md"]).rstrip() + "\n", encoding="utf-8")
    (tdir / "solution.py").write_text(str(item["solution_py"]).rstrip() + "\n", encoding="utf-8")
    (gdir / "partial.py").write_text(str(item["partial_py"]).rstrip() + "\n", encoding="utf-8")
    (gdir / "reference.py").write_text(str(item["reference_py"]).rstrip() + "\n", encoding="utf-8")
    (gdir / "cases.json").write_text(json.dumps(item["cases_json"], indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    verdict = check_task(tdir, gdir)
    return raw_id, verdict


def run_batch_on_key(key_idx: int, key: str, batches: list[tuple[str, str]], out_root: Path,
                     tasks_per_batch: int, tracker: UsageTracker) -> list[dict]:
    session_id = f"ses_oca_delim_k{key_idx}_v2"
    prefix_turns = [
        {"role": "user", "parts": [{"text": SHARED_GUIDE_PROMPT}]},
        {"role": "model", "parts": [{"text": "Understood. Send the batch specification and I will emit the tasks using the exact ===TASK_START=== and ---FILE:...--- delimiters."}]},
    ]
    warmed = False
    accepted = []

    for batch_id, domain in batches:
        batch_dir = out_root / f"tasks-{batch_id}"
        existing_manifest = batch_dir / "manifest.json"
        if existing_manifest.is_file():
            existing_rows = json.loads(existing_manifest.read_text(encoding="utf-8")).get("tasks") or []
            if len(existing_rows) >= max(1, tasks_per_batch - 1):
                accepted.extend(existing_rows)
                print(f"[k{key_idx}:{batch_id}] already complete ({len(existing_rows)} valid), skipping", flush=True)
                continue
        batch_dir.mkdir(parents=True, exist_ok=True)
        user_msg = (
            f"Batch ID prefix: `{batch_id}`\n"
            f"Domain focus: {domain}\n\n"
            f"Author {tasks_per_batch} distinct, self-contained tasks in this domain using the exact `===TASK_START ...===` / `---FILE:...---` / `===TASK_END===` format. "
            f"Every task `id` MUST start with `{batch_id}-`. "
            f"Keep code tight and idiomatic (50-85 lines per `solution.py`, no verbose docstrings, 8-10 crisp cases in `cases.json`). "
            f"Plant 2-3 independent realistic bugs in `solution.py`; `partial.py` fixes >=1 bug while leaving >=1 bug unfixed; "
            f"`reference.py` passes 100% of `cases.json`."
        )
        contents = [*prefix_turns, {"role": "user", "parts": [{"text": user_msg}]}]
        t0 = time.time()
        try:
            text, was_api = call_argon(key, session_id, contents, tracker)
            if was_api and not warmed:
                warmed = True
                time.sleep(6.5)
            items = parse_delimited_tasks(text)
            if not items:
                raise ValueError("no ===TASK_START=== blocks parsed")
        except Exception as e:
            print(f"[k{key_idx}:{batch_id}] generation error: {e}", flush=True)
            continue

        good_rows = []
        failed_items = []
        for item in items:
            try:
                tid, res = materialize_and_check(batch_dir, item, batch_id)
            except Exception as e:
                tid, res = item.get("id", "unknown"), {"ok": False, "problems": [repr(e)]}
            if res["ok"]:
                lines = len(str(item.get("solution_py", "")).splitlines())
                row = {"id": tid, "split": "pool", "domain": batch_id[:3],
                       "bugs": int(item.get("bugs") or 2), "lines": lines, "passed": res.get("passed")}
                good_rows.append(row)
            else:
                failed_items.append((tid, item, res["problems"]))

        # Multi-turn cached self-repair for any failed items in this batch (reuses contents + draft in cache!)
        if failed_items:
            repair_spec = "\n".join(f"- `{tid}` failed validation: {probs}" for tid, _, probs in failed_items)
            repair_prompt = (
                f"The following {len(failed_items)} task(s) from your response failed `oca.validate`:\n"
                f"{repair_spec}\n\n"
                f"Emit ONLY the corrected `===TASK_START ...=== ... ===TASK_END===` block(s) for those {len(failed_items)} task(s) "
                f"(keep the same task `id`s; fix `reference.py`, `partial.py`, `solution.py`, `TASK.md`, or `cases.json` so every gate passes)."
            )
            repair_contents = [
                *contents,
                {"role": "model", "parts": [{"text": text}]},
                {"role": "user", "parts": [{"text": repair_prompt}]},
            ]
            try:
                rtext, _ = call_argon(key, session_id, repair_contents, tracker, temperature=0.2)
                for item in parse_delimited_tasks(rtext):
                    tid, res = materialize_and_check(batch_dir, item, batch_id)
                    if res["ok"] and tid not in {r["id"] for r in good_rows}:
                        lines = len(str(item.get("solution_py", "")).splitlines())
                        good_rows.append({"id": tid, "split": "pool", "domain": batch_id[:3],
                                          "bugs": int(item.get("bugs") or 2), "lines": lines,
                                          "passed": res.get("passed"), "repaired": True})
            except Exception as e:
                print(f"[k{key_idx}:{batch_id}] repair skipped: {e}", flush=True)

        # Clean up any invalid leftover directories so `oca.validate` on `batch_dir` is 100% green
        valid_ids = {r["id"] for r in good_rows}
        for sub in ("tasks", "grader"):
            sdir = batch_dir / sub
            if sdir.is_dir():
                for child in sdir.iterdir():
                    if child.name not in valid_ids:
                        shutil.rmtree(child, ignore_errors=True)
        (batch_dir / "manifest.json").write_text(json.dumps({"tasks": good_rows}, indent=2) + "\n", encoding="utf-8")
        accepted.extend(good_rows)
        print(f"[k{key_idx}:{batch_id}] {len(good_rows)}/{len(items)} valid in {time.time()-t0:.1f}s | {tracker.summary()}",
              flush=True)
    return accepted


def assign_splits(out_root: Path, heldout_per_domain: int = 2, pattern: str = "tasks-*/manifest.json"):
    """Deterministic domain-stratified split: heldout tasks are isolated from training tasks."""
    manifests = sorted(out_root.glob(pattern))
    by_dom: dict[str, list[tuple[Path, dict]]] = {}
    for mpath in manifests:
        data = json.loads(mpath.read_text(encoding="utf-8"))
        for row in data["tasks"]:
            by_dom.setdefault(row.get("domain", mpath.parent.name), []).append((mpath, row))

    counts = {"train": 0, "heldout": 0}
    rewritten: dict[Path, list[dict]] = {m: [] for m in manifests}
    for dom, items in sorted(by_dom.items()):
        items_sorted = sorted(items, key=lambda x: hashlib.sha256(x[1]["id"].encode()).hexdigest())
        n_hold = min(heldout_per_domain, max(1, len(items_sorted) // 4))
        for idx, (mpath, row) in enumerate(items_sorted):
            row["split"] = "heldout" if idx < n_hold else "train"
            counts[row["split"]] += 1
            rewritten[mpath].append(row)

    for mpath, rows in rewritten.items():
        rows.sort(key=lambda r: r["id"])
        mpath.write_text(json.dumps({"tasks": rows}, indent=2) + "\n", encoding="utf-8")
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keys-file", type=Path, required=True, help="File with one oc_sk_... key per line")
    ap.add_argument("--out-root", type=Path, default=ROOT / "data")
    ap.add_argument("--tasks-per-batch", type=int, default=2)
    ap.add_argument("--subdivide", type=int, default=2, help="Split each domain spec into N focused micro-batches")
    ap.add_argument("--limit-batches", type=int, default=0, help="0 = all batches")
    ap.add_argument("--workers", type=int, default=10, help="Parallel worker threads across keys")
    ap.add_argument("--model", default="hy4-flash-free", help="gemini-4-argon or hy4-flash-free")
    args = ap.parse_args()
    global _FALLBACK_FREE
    if args.model != "gemini-4-argon":
        _FALLBACK_FREE = True

    keys = [ln.strip() for ln in args.keys_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not keys:
        raise SystemExit("No API keys found in --keys-file")
    expanded = []
    angles = (
        "Focus on stateful operations (`run(ops)`), state transitions, and subtle boundary resets.",
        "Focus on pure algorithmic/parsing functions, tie-breaking rules, and tricky input edge cases.",
        "Focus on error handling (`ValueError`/`KeyError`), invariants, and multi-helper composition.",
    )
    for bid, dom in BATCH_SPECS:
        if args.subdivide <= 1:
            expanded.append((bid, dom))
        else:
            for s in range(args.subdivide):
                expanded.append((f"{bid}{s+1}", f"{dom} — {angles[s % len(angles)]}"))
    specs = expanded[:args.limit_batches] if args.limit_batches > 0 else expanded
    n_workers = max(1, args.workers)
    shards: list[list[tuple[str, str]]] = [[] for _ in range(n_workers)]
    for idx, spec in enumerate(specs):
        shards[idx % n_workers].append(spec)

    tracker = UsageTracker()
    args.out_root.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    all_rows = []
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futs = [
            pool.submit(run_batch_on_key, wi, keys[wi % len(keys)], shards[wi], args.out_root,
                        args.tasks_per_batch, tracker)
            for wi in range(n_workers) if shards[wi]
        ]
        for f in as_completed(futs):
            all_rows.extend(f.result())

    splits = assign_splits(args.out_root, heldout_per_domain=3, pattern="tasks-d*/manifest.json")
    summary = {
        "total_valid_generated": len(all_rows),
        "splits": splits,
        "elapsed_s": round(time.time() - t0, 1),
        "usage": tracker.summary(),
    }
    (args.out_root / "generation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("\n=== GENERATION COMPLETE ===", flush=True)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
