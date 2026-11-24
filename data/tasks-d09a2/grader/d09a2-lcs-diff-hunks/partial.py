from typing import Any

Op = dict[str, Any]


def _make_op(kind: str, a_start: int, a_end: int, b_start: int, b_end: int) -> Op:
    return {
        "op": kind,
        "a_start": a_start,
        "a_end": a_end,
        "b_start": b_start,
        "b_end": b_end,
    }


def _lcs_table(a: list[str], b: list[str]) -> list[list[int]]:
    n = len(a)
    m = len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if a[i] == b[j]:
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    return dp


def _raw_ops(a: list[str], b: list[str], dp: list[list[int]]) -> list[Op]:
    n = len(a)
    m = len(b)
    i = 0
    j = 0
    ops: list[Op] = []
    while i < n or j < m:
        if i < n and j < m and a[i] == b[j]:
            ops.append(_make_op("equal", i, i + 1, j, j + 1))
            i += 1
            j += 1
        elif j == m or (i < n and dp[i + 1][j] >= dp[i][j + 1]):
            ops.append(_make_op("delete", i, i + 1, j, j))
            i += 1
        else:
            ops.append(_make_op("insert", i, i, j, j + 1))
            j += 1
    return ops


def _coalesce(ops: list[Op]) -> list[Op]:
    hunks: list[Op] = []
    for op in ops:
        hunks.append(dict(op))
    return hunks


def diff_hunks(a: list[str], b: list[str]) -> list[Op]:
    dp = _lcs_table(a, b)
    return _coalesce(_raw_ops(a, b, dp))
