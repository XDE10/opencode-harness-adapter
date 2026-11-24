def _split_paragraphs(text: str) -> list[list[str]]:
    normalized = text.replace("\r\n", "\n")
    paragraphs: list[list[str]] = []
    current: list[str] = []
    for raw_line in normalized.split("\n"):
        if not raw_line.strip():
            if current:
                paragraphs.append(" ".join(current).split())
                current.clear()
        else:
            current.append(raw_line)
    if current:
        paragraphs.append(" ".join(current).split())
    return paragraphs


def _wrap_paragraph(
    words: list[str],
    width: int,
    indent: int,
    hanging_indent: int,
    break_long_words: bool,
) -> list[str]:
    lines: list[str] = []
    cur = ""
    first_prefix = " " * indent
    cont_prefix = " " * hanging_indent

    def cur_avail() -> int:
        return (width - indent) if not lines else (width - hanging_indent)

    def flush(line_text: str) -> None:
        prefix = first_prefix if not lines else cont_prefix
        lines.append(prefix + line_text)

    for word in words:
        avail = cur_avail()
        if not cur:
            if len(word) <= avail:
                cur = word
            elif not break_long_words:
                flush(word)
            else:
                pos = 0
                while pos < len(word):
                    step = cur_avail()
                    chunk = word[pos : pos + step]
                    pos += step
                    if pos < len(word):
                        flush(chunk)
                    else:
                        cur = chunk
        elif len(cur) + 1 + len(word) <= avail:
            cur = cur + " " + word
        else:
            flush(cur)
            cur = ""
            next_avail = cur_avail()
            if len(word) <= next_avail:
                cur = word
            elif not break_long_words:
                flush(word)
            else:
                pos = 0
                while pos < len(word):
                    step = cur_avail()
                    chunk = word[pos : pos + step]
                    pos += step
                    if pos < len(word):
                        flush(chunk)
                    else:
                        cur = chunk
    if cur:
        flush(cur)
    return lines


def wrap_hanging(text, width=72, indent=0, hanging_indent=4, break_long_words=False):
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    if isinstance(width, bool) or not isinstance(width, int) or width < 1:
        raise ValueError("width must be an integer >= 1")
    if isinstance(indent, bool) or not isinstance(indent, int) or indent < 0:
        raise ValueError("indent must be a non-negative integer")
    if isinstance(hanging_indent, bool) or not isinstance(hanging_indent, int) or hanging_indent < 0:
        raise ValueError("hanging_indent must be a non-negative integer")
    if not isinstance(break_long_words, bool):
        raise ValueError("break_long_words must be a boolean")

    if width <= indent or width <= hanging_indent:
        raise ValueError("width must exceed both indent and hanging_indent")

    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return ""
    rendered = [
        "\n".join(_wrap_paragraph(words, width, indent, hanging_indent, break_long_words))
        for words in paragraphs
    ]
    return "\n\n".join(rendered)
