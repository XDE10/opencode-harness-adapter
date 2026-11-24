import re

_UNITS = (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1))
_UNIT_SET = {unit for unit, _ in _UNITS}
_TERM_RE = re.compile(r"([0-9]+)([wdhms])")


def _parse_term(chunk):
    match = _TERM_RE.fullmatch(chunk)
    if match is None:
        raise ValueError("invalid duration term")
    return int(match.group(1)), match.group(2)


def _parse(text):
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if text == "":
        raise ValueError("empty duration")
    totals = {unit: 0 for unit in _UNIT_SET}
    for chunk in text.split(" "):
        amount, unit = _parse_term(chunk)
        totals[unit] = amount
    total = 0
    for unit, seconds in _UNITS:
        total += totals[unit] * seconds
    return total


def _decompose(total):
    if total == 0:
        return [(0, "s")]
    remaining = total
    parts = []
    for unit, seconds in _UNITS:
        count, remaining = divmod(remaining, seconds)
        if count:
            parts.append((count, unit))
    return parts


def _render_part(count, unit, first):
    if first:
        return f"{count}{unit}"
    return f"{count:02d}{unit}"


def _format(parts):
    if len(parts) == 1:
        return _render_part(parts[0][0], parts[0][1], True)
    chunks = []
    for index, (count, unit) in enumerate(parts):
        chunks.append(_render_part(count, unit, index == 0))
    return " ".join(chunks)


def canonical_duration(text):
    total = _parse(text)
    parts = _decompose(total)
    return _format(parts)
