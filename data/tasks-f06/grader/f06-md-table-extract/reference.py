import re

_SEP_RE = re.compile(r"^:?-{3,}:?$")


def _split_cells(raw_line: str) -> list[str]:
    text = raw_line.strip()
    if not text:
        raise ValueError("empty line inside table")
    cells: list[str] = []
    buf: list[str] = []
    backslashes = 0
    for ch in text:
        if ch == "|" and backslashes % 2 == 0:
            cells.append("".join(buf))
            buf.clear()
            backslashes = 0
        else:
            buf.append(ch)
            backslashes = backslashes + 1 if ch == "\\" else 0
    cells.append("".join(buf))
    if len(cells) > 1 and cells[0] == "":
        cells.pop(0)
    if len(cells) > 1 and cells[-1] == "":
        cells.pop()
    return cells


def _unescape_cell(cell: str) -> str:
    out: list[str] = []
    i = 0
    n = len(cell)
    while i < n:
        if cell[i] == "\\" and i + 1 < n and cell[i + 1] in ("\\", "|"):
            out.append(cell[i + 1])
            i += 2
        else:
            out.append(cell[i])
            i += 1
    return "".join(out)


def parse_markdown_table(text, trim=True, unescape=True):
    if not isinstance(text, str):
        raise ValueError("text must be a string")

    raw_lines = [line.rstrip("\r") for line in text.split("\n")]
    while raw_lines and not raw_lines[0].strip():
        raw_lines.pop(0)
    while raw_lines and not raw_lines[-1].strip():
        raw_lines.pop()

    if len(raw_lines) < 2:
        raise ValueError("table must have header and separator rows")
    if any(not line.strip() for line in raw_lines):
        raise ValueError("blank line inside table")

    raw_headers = _split_cells(raw_lines[0])
    sep_cells = _split_cells(raw_lines[1])
    if len(sep_cells) != len(raw_headers) or any(not _SEP_RE.match(c.strip()) for c in sep_cells):
        raise ValueError("invalid separator row")

    headers: list[str] = []
    seen: set[str] = set()
    for h in raw_headers:
        val = h.strip() if trim else h
        if unescape:
            val = _unescape_cell(val)
        if not val:
            raise ValueError("empty header name")
        if val in seen:
            raise ValueError("duplicate header name")
        seen.add(val)
        headers.append(val)

    ncols = len(headers)
    records: list[dict[str, str]] = []
    for raw in raw_lines[2:]:
        cells = _split_cells(raw)
        if len(cells) > ncols:
            raise ValueError("row has too many columns")
        if len(cells) < ncols:
            cells.extend([""] * (ncols - len(cells)))
        row_dict: dict[str, str] = {}
        for key, cell in zip(headers, cells):
            val = cell.strip() if trim else cell
            if unescape:
                val = _unescape_cell(val)
            row_dict[key] = val
        records.append(row_dict)
    return records
