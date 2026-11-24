from itertools import zip_longest


def _wrap_cell(text: str, width: int | None) -> list[str]:
    raw_lines = text.split("\n")
    if width is None:
        return raw_lines
    wrapped: list[str] = []
    for raw in raw_lines:
        words = raw.split()
        if not words:
            wrapped.append("")
            continue
        cur = ""
        for word in words:
            if len(word) > width:
                if cur:
                    wrapped.append(cur)
                    cur = ""
                for i in range(0, len(word), width):
                    chunk = word[i : i + width]
                    if len(chunk) == width:
                        wrapped.append(chunk)
                    else:
                        cur = chunk
            elif not cur:
                cur = word
            elif len(cur) + 1 + len(word) <= width:
                cur = cur + " " + word
            else:
                wrapped.append(cur)
                cur = word
        if cur:
            wrapped.append(cur)
    return wrapped


def _render_row_lines(cells: list[str], widths: list[int], pad: int, wrap: bool) -> list[str]:
    columns = [_wrap_cell(cell, w if wrap else None) for cell, w in zip(cells, widths)]
    spacer = " " * pad
    out: list[str] = []
    for line_tuple in zip_longest(*columns, fillvalue=""):
        parts = [spacer + line.ljust(w) + spacer for line, w in zip(line_tuple, widths)]
        out.append("|" + "|".join(parts) + "|")
    return out


def render_box_table(headers, rows, col_widths=None, padding=1):
    if not isinstance(headers, list) or not headers or not all(isinstance(h, str) for h in headers):
        raise ValueError("headers must be a non-empty list of strings")
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    ncols = len(headers)
    for row in rows:
        if not isinstance(row, list) or len(row) != ncols or not all(isinstance(c, str) for c in row):
            raise ValueError("each row must be a list of strings matching header length")

    if isinstance(padding, bool) or not isinstance(padding, int) or padding < 0:
        raise ValueError("padding must be a non-negative integer")
    pad = padding

    wrap = col_widths is not None
    if col_widths is not None:
        if (
            not isinstance(col_widths, list)
            or len(col_widths) != ncols
            or any(isinstance(w, bool) or not isinstance(w, int) or w < 1 for w in col_widths)
        ):
            raise ValueError("col_widths must match header length with widths >= 1")
        widths = list(col_widths)
    else:
        widths = [1] * ncols
        for row in [headers, *rows]:
            for idx, cell in enumerate(row):
                for line in cell.split("\n"):
                    if len(line) > widths[idx]:
                        widths[idx] = len(line)

    border = "+" + "+".join("-" * (w + 2 * pad) for w in widths) + "+"
    lines = [border]
    lines.extend(_render_row_lines(headers, widths, pad, wrap))
    lines.append(border)
    for row in rows:
        lines.extend(_render_row_lines(row, widths, pad, wrap))
        lines.append(border)
    return "\n".join(lines)
