"""Offline trajectory attribution & non-thinking reasoning-leakage auditor (0 GPU cost).

Directly addresses open questions raised around Hugging Face's Harness Adapters (Nov 2026):
- What behavioral changes do harness-adapted LoRAs actually learn (tool mix, turn count,
  edit-before-test discipline, error recovery)?
- Do non-thinking harness-adapted LoRAs exhibit short chain-of-thought / `<think>` reasoning
  leakage when `enable_thinking=False`?
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import statistics

_THINK_TAG_RE = re.compile(r"</?think>", re.IGNORECASE)
_COT_PREAMBLE_RE = re.compile(
    r"(?:^|\n)\s*(?:let me think|let's think|step\s+1\s*:|first,\s+let me|wait,\s+|actually,\s+let me|hmm,)",
    re.IGNORECASE,
)
_FAIL_OUTPUT_RE = re.compile(r"(?:FAILED|Traceback \(most recent call last\)|AssertionError|SyntaxError|exit code [1-9])")


def detect_reasoning_leakage(content: str, completion_tokens: int = 0) -> dict:
    """Detect explicit `<think>` tags or unprompted CoT monologue leakage in non-thinking turns."""
    text = content or ""
    has_think_tag = bool(_THINK_TAG_RE.search(text))
    has_cot_preamble = bool(_COT_PREAMBLE_RE.search(text)) and (len(text) >= 240 or completion_tokens >= 80)
    return {
        "think_tag": has_think_tag,
        "cot_preamble": has_cot_preamble,
        "leaked": has_think_tag or has_cot_preamble,
        "text_chars": len(text),
    }


def audit_trial(rec: dict) -> dict:
    """Extract behavioral, tool-use, error-recovery, and reasoning-leakage metrics from one trial."""
    turns = [t for t in (rec.get("turns") or []) if not t.get("aux")]
    tool_counts: Counter[str] = Counter()
    leaked_turns = 0
    think_tag_turns = 0
    cot_preamble_turns = 0
    safe_intercepts = 0
    had_tool_error = False

    for t in turns:
        msg = t.get("message") or {}
        content = msg.get("content") or ""
        t_toks = len(t.get("completion_token_ids") or [])
        leak = detect_reasoning_leakage(content, completion_tokens=t_toks)
        if leak["leaked"]:
            leaked_turns += 1
        if leak["think_tag"]:
            think_tag_turns += 1
        if leak["cot_preamble"]:
            cot_preamble_turns += 1
        if t.get("safe_intercepted"):
            safe_intercepts += 1
        for tc in (msg.get("tool_calls") or []):
            fn = ((tc.get("function") or {}).get("name") or "unknown").lower()
            tool_counts[fn] += 1
        # Check whether prior user/tool feedback contained test/runtime failure
        req_msgs = (t.get("request_messages") or [])
        if req_msgs:
            last_ctx = str(req_msgs[-1].get("content") or "")
            if _FAIL_OUTPUT_RE.search(last_ctx):
                had_tool_error = True

    for m in (rec.get("last_request_messages") or []):
        if m.get("role") == "tool" and _FAIL_OUTPUT_RE.search(str(m.get("content") or "")):
            had_tool_error = True
            break
    if not tool_counts and rec.get("tool_calls"):
        for name in rec["tool_calls"]:
            tool_counts[str(name).lower()] += 1

    passed = (rec.get("grade") or {}).get("status") == "pass" and not rec.get("hack_flags")
    return {
        "trial_id": rec.get("trial_id", ""),
        "passed": bool(passed),
        "n_turns": len(turns) or int(rec.get("n_policy_turns", 0)),
        "completion_tokens": int(rec.get("completion_tokens", 0)),
        "tool_counts": dict(tool_counts),
        "total_tool_calls": sum(tool_counts.values()),
        "leaked_turns": leaked_turns,
        "think_tag_turns": think_tag_turns,
        "cot_preamble_turns": cot_preamble_turns,
        "had_reasoning_leak": leaked_turns > 0,
        "safe_intercepts": safe_intercepts,
        "had_tool_error": had_tool_error,
        "recovered_after_error": bool(had_tool_error and passed),
    }


def audit_records(records: list[dict]) -> dict:
    valid = [r for r in records if not r.get("error")]
    if not valid:
        return {"n_trials": 0}
    per = [audit_trial(r) for r in valid]
    n = len(per)
    tot_turns = max(1, sum(x["n_turns"] for x in per))
    err_trials = [x for x in per if x["had_tool_error"]]
    tool_totals: Counter[str] = Counter()
    for x in per:
        tool_totals.update(x["tool_counts"])
    tot_tools = max(1, sum(tool_totals.values()))
    return {
        "n_trials": n,
        "pass_rate": round(sum(x["passed"] for x in per) / n, 4),
        "mean_turns": round(statistics.mean(x["n_turns"] for x in per), 2),
        "mean_completion_tokens": round(statistics.mean(x["completion_tokens"] for x in per), 1),
        "mean_tool_calls": round(statistics.mean(x["total_tool_calls"] for x in per), 2),
        "reasoning_leak_trial_rate": round(sum(x["had_reasoning_leak"] for x in per) / n, 4),
        "reasoning_leak_turn_rate": round(sum(x["leaked_turns"] for x in per) / tot_turns, 4),
        "think_tag_turn_rate": round(sum(x["think_tag_turns"] for x in per) / tot_turns, 4),
        "cot_preamble_turn_rate": round(sum(x["cot_preamble_turns"] for x in per) / tot_turns, 4),
        "safe_intercept_total": sum(x["safe_intercepts"] for x in per),
        "error_encountered_trials": len(err_trials),
        "error_recovery_rate": (
            round(sum(x["recovered_after_error"] for x in err_trials) / len(err_trials), 4)
            if err_trials else None
        ),
        "tool_share": {k: round(v / tot_tools, 4) for k, v in tool_totals.most_common()},
    }


def audit_arm_dir(arm_dir: Path) -> dict:
    recs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(arm_dir.glob("*.json"))
            if p.name != "eval_report.json"]
    return audit_records(recs)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arm", action="append", required=True, help="label=dir_of_trial_jsons (repeatable)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = {}
    for spec in args.arm:
        label, path_str = spec.split("=", 1)
        out[label] = audit_arm_dir(Path(path_str))
    txt = json.dumps(out, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
