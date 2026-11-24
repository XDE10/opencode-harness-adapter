def expand_cron_field(field, low, high):
    _check_bounds(low, high)
    if type(field) is not str:
        raise ValueError
    result = set()
    for item in field.split(","):
        result.update(_expand_item(item, low, high))
    return sorted(result)


def _check_bounds(low, high):
    if type(low) is not int or type(high) is not int or low < 0 or low > high:
        raise ValueError


def _num(text):
    if not text or not text.isascii() or not text.isdigit():
        raise ValueError
    return int(text)


def _inside(value, low, high):
    if value < low or value > high:
        raise ValueError


def _parse_range(text, low, high):
    if text.count("-") != 1:
        raise ValueError
    left, right = text.split("-", 1)
    start = _num(left)
    end = _num(right)
    _inside(start, low, high)
    _inside(end, low, high)
    if start > end:
        raise ValueError
    return start, end


def _values(start, end, step, stepped):
    return range(start, end + 1, step)


def _expand_item(item, low, high):
    if not item:
        raise ValueError
    if "/" in item:
        parts = item.split("/")
        if len(parts) != 2:
            raise ValueError
        base, step_text = parts
        step = _num(step_text)
        if step <= 0:
            raise ValueError
        if base == "*":
            start, end = low, high
        elif "-" in base:
            start, end = _parse_range(base, low, high)
        else:
            start = _num(base)
            _inside(start, low, high)
            end = high
        return _values(start, end, step, True)
    if item == "*":
        return _values(low, high, 1, False)
    if "-" in item:
        start, end = _parse_range(item, low, high)
        return _values(start, end, 1, False)
    value = _num(item)
    _inside(value, low, high)
    return [value]
