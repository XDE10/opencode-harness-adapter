import re
from r14s1pkg.models import Hunk, HunkLine

_HUNK_HEADER_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$"
)
_IGNORE_PREFIXES = ("--- ", "+++ ", "diff --git ", "index ")


def parse_unified_diff(diff_text: str) -> list[Hunk]:
    hunks: list[Hunk] = []
    current_hunk: Hunk | None = None

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("@@"):
            if current_hunk is not None:
                current_hunk.validate()
                hunks.append(current_hunk)

            match = _HUNK_HEADER_RE.match(raw_line)
            if not match:
                raise ValueError(f"Malformed hunk header: {raw_line!r}")

            old_start = int(match.group(1))
            old_count = int(match.group(2)) if match.group(2) is not None else 1
            new_start = int(match.group(3))
            new_count = int(match.group(4)) if match.group(4) is not None else 1
            section = match.group(5).strip()

            current_hunk = Hunk(
                old_start=old_start,
                old_count=old_count,
                new_start=new_start,
                new_count=new_count,
                section=section,
            )
            continue

        if current_hunk is None:
            if raw_line.startswith(_IGNORE_PREFIXES) or not raw_line.strip():
                continue
            raise ValueError(f"Unexpected line outside hunk: {raw_line!r}")

        if raw_line.startswith("\\"):
            continue

        if raw_line == "":
            current_hunk.lines.append(HunkLine(op=" ", text=""))
        elif raw_line[0] in (" ", "+", "-"):
            current_hunk.lines.append(HunkLine(op=raw_line[0], text=raw_line[1:]))
        elif raw_line.startswith(_IGNORE_PREFIXES):
            current_hunk.validate()
            hunks.append(current_hunk)
            current_hunk = None
        else:
            raise ValueError(f"Invalid hunk body line: {raw_line!r}")

    if current_hunk is not None:
        current_hunk.validate()
        hunks.append(current_hunk)

    return hunks
