"""Audit, deduplicate, and domain-isolate generated single-file tasks under `data/`.

Steps:
1. Validate every generated task (`oca.validate.check_task`) and remove broken/empty dirs.
2. Detect near-duplicates across all generated tasks (and against v3 heldout) via:
   - Normalized slug keyword Jaccard
   - TASK.md word-bigram Jaccard
   - reference.py AST node-trigram Jaccard
   Keep one highest-quality representative per duplicate cluster.
3. Map every task to a canonical semantic domain cluster (merging overlapping `f01..f10`
   and `d01..d20` prefixes), then assign train/heldout STRICTLY BY DOMAIN CLUSTER
   so zero near-duplicate or same-domain leakage can occur across splits.
4. Rewrite clean `manifest.json` per directory and emit `data/clean_report.json`.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil

from . import ROOT
from .tasks import _v3
from .validate import check_task

# Canonical semantic domain mapping (merges f01..f10 with their matching d01..d20 domains)
DOMAIN_MAP = {
    "d01": "config_tabular",
    "f05": "config_tabular",
    "d02": "markup_tokenizer",
    "f06": "markup_tokenizer",
    "d03": "calendar_interval",
    "f08": "calendar_interval",
    "d04": "stateful_cache_kv",
    "f02": "stateful_cache_kv",
    "f10": "stateful_cache_kv",
    "d05": "money_numeric",
    "f03": "money_numeric",
    "d06": "graph_dependency",
    "f04": "graph_dependency",
    "d07": "text_formatting",
    "d08": "sequence_tree",
    "f09": "sequence_tree",
    "d09": "diff_interpreter",
    "f07": "diff_interpreter",
    "d10": "backend_codec",
    "d11": "log_routing",
    "f01": "log_routing",
    "d12": "grid_string_codec",
    "d13": "auction_ast",
    "d14": "data_quality_framing",
    "d15": "string_timeseries",
    "d16": "range_quota",
    "d17": "table_combinatorics",
    "d18": "vfs_buildgraph",
    "d19": "game_index",
    "d20": "wire_scheduler",
}

SLUG_STOPWORDS = {
    "run", "ops", "state", "stateful", "engine", "manager", "session",
    "loader", "parser", "handler", "system", "tracker", "builder", "eval",
    "evaluator", "simulator", "calculator", "planner", "checker", "codec",
}

# Fixed heldout semantic domains (~22-28% of deduped tasks, completely disjoint from train)
DEFAULT_HELDOUT_DOMAINS = {
    "calendar_interval",
    "graph_dependency",
    "diff_interpreter",
    "wire_scheduler",
    "data_quality_framing",
}


def canonical_domain(task_id: str, parent_dir_name: str) -> str:
    prefix = task_id.split("-")[0]
    m = re.match(r"^(d\d\d|f\d\d)", prefix)
    key = m.group(1) if m else parent_dir_name.replace("tasks-", "")[:3]
    return DOMAIN_MAP.get(key, key)


def slug_tokens(task_id: str) -> set[str]:
    parts = task_id.split("-")[1:] if "-" in task_id else [task_id]
    raw = [w.lower() for p in parts for w in p.split("_") if len(w) > 1]
    filtered = {w for w in raw if w not in SLUG_STOPWORDS}
    return filtered or set(raw)


def text_bigrams(text: str) -> set[tuple[str, str]]:
    words = re.findall(r"[a-z0-9_]{2,}", text.lower())
    return set(zip(words, words[1:])) if len(words) >= 2 else set()


def ast_trigrams(code: str) -> set[tuple[str, str, str]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    seq = [type(node).__name__ for node in ast.walk(tree)]
    return set(zip(seq, seq[1:], seq[2:])) if len(seq) >= 3 else set()


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def task_quality_score(rec: dict) -> tuple:
    # Prefer rich case count, ideal code length (60-120 lines), non-duplicate d* id
    lines = rec["lines"]
    len_penalty = -abs(lines - 85)
    is_d = 1 if rec["id"].startswith("d") else 0
    return (rec["cases"], len_penalty, is_d, rec["id"])


def clean_data(data_root: Path, dry_run: bool = False, heldout_domains: set[str] | None = None) -> dict:
    heldout_domains = heldout_domains or set(DEFAULT_HELDOUT_DOMAINS)
    v3_tasks = list(_v3())
    v3_sigs = []
    for t in v3_tasks:
        ref_code = (t.grader_dir / "reference.py").read_text(encoding="utf-8", errors="replace")
        v3_sigs.append({
            "id": t.id, "split": t.split,
            "slug": slug_tokens(f"v3-{t.id}"),
            "bigrams": text_bigrams((t.task_dir / "TASK.md").read_text(encoding="utf-8", errors="replace")),
            "ast": ast_trigrams(ref_code),
        })

    dirs = sorted(d for d in data_root.glob("tasks-*") if d.is_dir())
    total_scanned = 0
    valid_recs = []
    removed_invalid = []
    removed_empty_dirs = []

    for d in dirs:
        troot = d / "tasks"
        groot = d / "grader"
        tids = sorted(p.name for p in troot.iterdir() if p.is_dir()) if troot.is_dir() else []
        if not tids:
            removed_empty_dirs.append(d.name)
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)
            continue
        for tid in tids:
            total_scanned += 1
            tdir, gdir = troot / tid, groot / tid
            verdict = check_task(tdir, gdir)
            if not verdict["ok"]:
                removed_invalid.append({"dir": d.name, "id": tid, "problems": verdict["problems"]})
                if not dry_run:
                    shutil.rmtree(tdir, ignore_errors=True)
                    shutil.rmtree(gdir, ignore_errors=True)
                continue
            tmd = (tdir / "TASK.md").read_text(encoding="utf-8", errors="replace")
            sol = (tdir / "solution.py").read_text(encoding="utf-8", errors="replace")
            ref = (gdir / "reference.py").read_text(encoding="utf-8", errors="replace")
            cases_obj = json.loads((gdir / "cases.json").read_text(encoding="utf-8"))
            valid_recs.append({
                "dir": d, "dir_name": d.name, "id": tid,
                "domain": canonical_domain(tid, d.name),
                "lines": len(sol.splitlines()),
                "cases": len(cases_obj.get("cases", [])),
                "passed": verdict.get("passed"),
                "slug": slug_tokens(tid),
                "bigrams": text_bigrams(tmd),
                "ast": ast_trigrams(ref),
            })

    # Step 2a: Drop any generated task that collides with v3 tasks
    removed_v3_overlap = []
    filtered = []
    for rec in valid_recs:
        hit = None
        for vs in v3_sigs:
            if (jaccard(rec["slug"], vs["slug"]) >= 0.6
                    or jaccard(rec["bigrams"], vs["bigrams"]) >= 0.45):
                hit = vs["id"]
                break
        if hit:
            removed_v3_overlap.append({"id": rec["id"], "v3_match": hit})
            if not dry_run:
                shutil.rmtree(rec["dir"] / "tasks" / rec["id"], ignore_errors=True)
                shutil.rmtree(rec["dir"] / "grader" / rec["id"], ignore_errors=True)
        else:
            filtered.append(rec)

    # Step 2b: Cluster near-duplicates among generated tasks
    n = len(filtered)
    uf = UnionFind(n)
    dup_edges = []
    for i in range(n):
        for j in range(i + 1, n):
            sj = jaccard(filtered[i]["slug"], filtered[j]["slug"])
            tj = jaccard(filtered[i]["bigrams"], filtered[j]["bigrams"])
            aj = jaccard(filtered[i]["ast"], filtered[j]["ast"])
            if sj >= 0.50 or tj >= 0.35 or (aj >= 0.55 and sj >= 0.25):
                uf.union(i, j)
                dup_edges.append({
                    "a": filtered[i]["id"], "b": filtered[j]["id"],
                    "slug_j": round(sj, 3), "text_j": round(tj, 3), "ast_j": round(aj, 3),
                })

    clusters: dict[int, list[dict]] = defaultdict(list)
    for idx, rec in enumerate(filtered):
        clusters[uf.find(idx)].append(rec)

    kept = []
    removed_dups = []
    for members in clusters.values():
        members_sorted = sorted(members, key=task_quality_score, reverse=True)
        winner = members_sorted[0]
        kept.append(winner)
        for loser in members_sorted[1:]:
            removed_dups.append({"dropped": loser["id"], "kept": winner["id"], "domain": loser["domain"]})
            if not dry_run:
                shutil.rmtree(loser["dir"] / "tasks" / loser["id"], ignore_errors=True)
                shutil.rmtree(loser["dir"] / "grader" / loser["id"], ignore_errors=True)

    # Step 3: Strictly domain-disjoint split assignment
    by_dir: dict[Path, list[dict]] = defaultdict(list)
    split_counts = Counter()
    domain_splits: dict[str, dict] = {}
    for rec in sorted(kept, key=lambda r: r["id"]):
        sp = "heldout" if rec["domain"] in heldout_domains else "train"
        split_counts[sp] += 1
        dinfo = domain_splits.setdefault(rec["domain"], {"split": sp, "count": 0})
        dinfo["count"] += 1
        by_dir[rec["dir"]].append({
            "id": rec["id"],
            "split": sp,
            "domain": rec["domain"],
            "lines": rec["lines"],
            "cases": rec["cases"],
            "passed": rec["passed"],
        })

    # Rewrite manifests and prune directories that became empty after dedup
    pruned_after_dedup = []
    for d in sorted(d for d in data_root.glob("tasks-*") if d.is_dir()):
        rows = by_dir.get(d, [])
        if not rows:
            pruned_after_dedup.append(d.name)
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)
        else:
            if not dry_run:
                (d / "manifest.json").write_text(
                    json.dumps({"tasks": rows}, indent=2) + "\n", encoding="utf-8"
                )

    # Assert domain disjointness
    train_domains = {r["domain"] for rows in by_dir.values() for r in rows if r["split"] == "train"}
    held_domains = {r["domain"] for rows in by_dir.values() for r in rows if r["split"] == "heldout"}
    assert not (train_domains & held_domains), f"Domain leakage detected: {train_domains & held_domains}"

    report = {
        "dry_run": dry_run,
        "funnel": {
            "scanned_on_disk": total_scanned,
            "valid_triple_control": len(valid_recs),
            "after_v3_dedup": len(filtered),
            "after_near_dup_dedup": len(kept),
            "generated_train": split_counts["train"],
            "generated_heldout": split_counts["heldout"],
            "v3_train": sum(1 for t in v3_tasks if t.split == "train"),
            "v3_heldout": sum(1 for t in v3_tasks if t.split == "heldout"),
            "total_train": split_counts["train"] + sum(1 for t in v3_tasks if t.split == "train"),
            "total_heldout": split_counts["heldout"] + sum(1 for t in v3_tasks if t.split == "heldout"),
        },
        "domain_disjoint_verified": True,
        "heldout_domains": sorted(held_domains),
        "train_domains": sorted(train_domains),
        "domains": dict(sorted(domain_splits.items())),
        "removed_invalid": removed_invalid,
        "removed_v3_overlap": removed_v3_overlap,
        "removed_duplicates_count": len(removed_dups),
        "removed_duplicates": removed_dups,
        "dup_edges_detected": len(dup_edges),
        "removed_empty_dirs": removed_empty_dirs,
        "pruned_after_dedup": pruned_after_dedup,
    }
    if not dry_run:
        (data_root / "clean_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", type=Path, default=ROOT / "data")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rep = clean_data(args.data_root, dry_run=args.dry_run)
    print(json.dumps({k: v for k, v in rep.items() if k not in ("removed_duplicates",)}, indent=2))
    print(f"Duplicates dropped ({rep['removed_duplicates_count']}):")
    for row in rep["removed_duplicates"]:
        print(f"  - {row['dropped']}  (kept: {row['kept']})")


if __name__ == "__main__":
    main()
