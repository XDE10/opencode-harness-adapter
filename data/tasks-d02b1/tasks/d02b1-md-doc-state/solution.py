import re


def _make_base_slug(text: str) -> str:
    cleaned = text.replace("`", "").lower()
    cleaned = re.sub(r"[^a-z0-9 -]", "", cleaned)
    cleaned = re.sub(r"[ -]+", "-", cleaned).strip("-")
    return cleaned or "section"


def _render_with_code_spans(line: str, defs: dict, ref_order: dict) -> str:
    out = []
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "`":
            end = line.find("`", i + 1)
            if end != -1:
                out.append(line[i : end + 1])
                i = end + 1
                continue
        if line.startswith("[^", i):
            close = line.find("]", i + 2)
            if close != -1 and "`" not in line[i + 2 : close] and close > i + 2:
                raw_label = line[i + 2 : close]
                norm = raw_label.strip().lower()
                if norm not in defs:
                    raise KeyError(norm)
                if norm not in ref_order:
                    ref_order[norm] = len(ref_order) + 1
                out.append(f"[{ref_order[norm]}]")
                i = close + 1
                continue
        out.append(line[i])
        i += 1
    return "".join(out)


def run_markdown_session(ops: list[dict]) -> list:
    toc = []
    slug_counts = {}
    footnote_defs = {}
    footnote_nums = {}
    results = []

    for item in ops:
        op = item.get("op")
        if op == "heading":
            level = item.get("level")
            if not isinstance(level, int) or isinstance(level, bool) or not (1 <= level <= 6):
                raise ValueError("Invalid heading level")
            base = _make_base_slug(item.get("text", ""))
            count = slug_counts.get(base, 0)
            slug_counts[base] = count + 1
            slug = base if count == 0 else f"{base}-{count}"
            entry = {"level": level, "slug": slug}
            toc.append(entry)
            results.append(entry)

        elif op == "footnote_def":
            label = item.get("label", "").strip().lower()
            if not label:
                raise ValueError("Empty footnote label")
            footnote_defs[label] = item.get("text", "").strip()
            results.append(None)

        elif op == "render_line":
            rendered = _render_with_code_spans(item.get("line", ""), footnote_defs, footnote_nums)
            results.append(rendered)

        elif op == "export":
            ordered_notes = sorted(
                ([num, footnote_defs[lbl]] for lbl, num in footnote_nums.items()),
                key=lambda pair: pair[0],
            )
            results.append({"toc": list(toc), "footnotes": ordered_notes})

        elif op == "reset":
            toc.clear()
            slug_counts.clear()
            footnote_defs.clear()
            results.append(None)

        else:
            raise ValueError(f"Unknown op: {op}")

    return results
