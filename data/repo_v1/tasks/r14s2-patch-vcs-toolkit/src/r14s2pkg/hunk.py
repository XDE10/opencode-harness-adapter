from __future__ import annotations
from dataclasses import dataclass
import re

HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(ValueError):
    """Raised when a unified diff cannot be parsed or applied."""


@dataclass(frozen=True)
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: tuple[str, ...]

    def source_lines(self) -> list[str]:
        return [line[1:] for line in self.lines if line.startswith((" ", "-"))]

    def target_lines(self) -> list[str]:
        return [line[1:] for line in self.lines if line.startswith((" ", "+"))]


def parse_unified_diff(diff_text: str) -> list[Hunk]:
    raw_lines = diff_text.splitlines()
    hunks: list[Hunk] = []
    current_header: tuple[int, int, int, int] | None = None
    current_lines: list[str] = []

    for line in raw_lines:
        if line.startswith(("---", "+++")):
            if current_header is None:
                continue
        match = HUNK_HEADER_RE.match(line)
        if match:
            if current_header is not None:
                hunks.append(_build_hunk(current_header, current_lines))
            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            current_header = (old_start, old_count, new_start, new_count)
            current_lines = []
        elif current_header is not None:
            if line.startswith((" ", "+", "-")):
                current_lines.append(line)
            elif line.startswith("\\"):
                continue
            else:
                raise PatchError(f"Invalid hunk line: {line!r}")

    if current_header is not None:
        hunks.append(_build_hunk(current_header, current_lines))

    if not hunks:
        raise PatchError("No valid hunks found in diff")
    return hunks


def _build_hunk(header: tuple[int, int, int, int], lines: list[str]) -> Hunk:
    old_start, old_count, new_start, new_count = header
    hunk = Hunk(old_start, old_count, new_start, new_count, tuple(lines))
    if len(hunk.source_lines()) != old_count or len(hunk.target_lines()) != new_count:
        raise PatchError(
            f"Hunk line count mismatch for @@ -{old_start},{old_count} +{new_start},{new_count} @@"
        )
    return hunk
