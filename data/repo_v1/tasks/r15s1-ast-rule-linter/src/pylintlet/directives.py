from __future__ import annotations

from dataclasses import dataclass
import re
import tokenize
import io


@dataclass(frozen=True, order=True)
class Diagnostic:
    line: int
    col: int
    code: str
    message: str

    def format(self) -> str:
        return f"{self.line}:{self.col}: {self.code} {self.message}"


NOQA_PATTERN = re.compile(r"#\s*noqa\b(?::\s*(.*))?", re.IGNORECASE)


class SuppressionMap:
    def __init__(self, mapping: dict[int, set[str] | None] | None = None) -> None:
        self._mapping: dict[int, set[str] | None] = mapping or {}

    def is_suppressed(self, line: int, code: str) -> bool:
        if line not in self._mapping:
            return False
        target = self._mapping[line]
        if target is None:
            return True
        return code in target


def parse_suppressions(source: str) -> SuppressionMap:
    mapping: dict[int, set[str] | None] = {}
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for tok_type, tok_str, (srow, _), _, _ in tokens:
        if tok_type != tokenize.COMMENT:
            continue
        match = NOQA_PATTERN.search(tok_str)
        if not match:
            continue
        raw_codes = match.group(1)
        if raw_codes is None:
            mapping[srow] = None
        else:
            codes = {part.strip() for part in raw_codes.split(",") if part.strip()}
            mapping[srow] = codes
    return SuppressionMap(mapping)
