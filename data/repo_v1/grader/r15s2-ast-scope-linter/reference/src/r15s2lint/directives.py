from __future__ import annotations

from dataclasses import dataclass
import io
import re
import tokenize


@dataclass(frozen=True, order=True)
class Diagnostic:
    line: int
    code: str
    message: str
    symbol: str = ""


_NOQA_RE = re.compile(r"#\s*noqa(?::\s*([A-Za-z0-9_,\s]+))?", re.IGNORECASE)


class SuppressionIndex:
    """Tracks line-level # noqa directives (blanket or rule-specific)."""

    def __init__(self, line_map: dict[int, set[str] | None] | None = None) -> None:
        self._line_map: dict[int, set[str] | None] = dict(line_map or {})

    def is_suppressed(self, line: int, code: str) -> bool:
        if line not in self._line_map:
            return False
        allowed = self._line_map[line]
        if allowed is None:
            return True
        return code.upper() in allowed

    def suppressed_lines(self) -> set[int]:
        return set(self._line_map.keys())


def parse_noqa_map(source: str) -> SuppressionIndex:
    line_map: dict[int, set[str] | None] = {}
    reader = io.StringIO(source).readline
    try:
        tokens = list(tokenize.generate_tokens(reader))
    except tokenize.TokenError:
        tokens = []

    for tok_type, tok_str, (sline, _), _, _ in tokens:
        if tok_type != tokenize.COMMENT:
            continue
        match = _NOQA_RE.search(tok_str)
        if not match:
            continue
        raw_codes = match.group(1)
        if raw_codes is None:
            line_map[sline] = None
        else:
            codes: set[str] = set()
            for part in raw_codes.split(","):
                tokens_in_part = part.strip().split()
                if tokens_in_part:
                    codes.add(tokens_in_part[0].upper())
            if codes:
                line_map[sline] = codes
            else:
                line_map[sline] = None
    return SuppressionIndex(line_map)
