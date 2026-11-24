def _has_unescaped_trailing_pipe(s: str) -> bool:
    if not s.endswith("|"):
        return False
    return not s.endswith("\\|")


def _split_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if _has_unescaped_trailing_pipe(s):
        s = s[:-1]

    cells = []
    buf = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "`":
            end = s.find("`", i + 1)
            if end != -1:
                buf.append(s[i : end + 1])
                i = end + 1
                continue
        if ch == "\\":
            if i + 1 < n and s[i + 1] in ("|", "\\"):
                buf.append(s[i + 1])
                i += 2
                continue
        if ch == "|":
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def _parse_align(cell: str) -> str:
    if not cell:
        raise ValueError("Empty delimiter cell")
    left = cell.startswith(":")
    right = cell.endswith(":")
    core = cell[1 if left else 0 : len(cell) - 1 if right else len(cell)]
    if len(core) < 3 or any(c != "-" for c in core):
        raise ValueError(f"Invalid delimiter: {cell}")
    if left and right:
        return "center"
    if right:
        return "right"
    return "left"


def parse_markdown_table(lines: list[str]) -> dict:
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1

    active = lines[start:end]
    if len(active) < 2:
        raise ValueError("Table requires header and delimiter rows")
    for ln in active:
        if not ln.strip():
            raise ValueError("Blank line inside table")

    headers = _split_cells(active[0])
    ncols = len(headers)
    if ncols == 0:
        raise ValueError("No columns")

    delim_cells = _split_cells(active[1])
    if len(delim_cells) != ncols:
        raise ValueError("Delimiter column count mismatch")
    align = [_parse_align(c) for c in delim_cells]

    rows = []
    for ln in active[2:]:
        row = _split_cells(ln)
        if len(row) > ncols:
            raise ValueError("Too many cells in row")
        if len(row) < ncols:
            row.extend([""] * (ncols - len(row)))
        rows.append(row)

    return {"headers": headers, "align": align, "rows": rows}
