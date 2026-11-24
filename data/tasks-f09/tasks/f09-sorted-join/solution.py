_VALID_HOW = ("inner", "left", "right", "outer")


def _parse_side(rows, side_name):
    parsed = []
    prev_key = None
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            raise ValueError(f"{side_name} items must be 2-element pairs")
        key, val = row
        if isinstance(key, bool) or not isinstance(key, int):
            raise ValueError(f"{side_name} key must be an integer")
        if prev_key and key < prev_key:
            raise ValueError(f"{side_name} must be sorted by key")
        prev_key = key
        parsed.append((key, val))
    return parsed


def sorted_merge_join(left, right, how="inner"):
    if how not in _VALID_HOW:
        raise ValueError(f"invalid join mode: {how}")

    left_rows = _parse_side(left, "left")
    right_rows = _parse_side(right, "right")

    i = 0
    j = 0
    n_left = len(left_rows)
    n_right = len(right_rows)
    result = []

    while i < n_left and j < n_right:
        l_key, l_val = left_rows[i]
        r_key, r_val = right_rows[j]

        if l_key == r_key:
            result.append([l_key, l_val, r_val])
            i += 1
            j += 1
        elif l_key < r_key:
            if how in ("left", "outer"):
                result.append([l_key, l_val, None])
            i += 1
        else:
            if how in ("right", "outer"):
                result.append([r_key, None, r_val])
            j += 1

    if how in ("left", "outer"):
        while i < n_left:
            l_key, l_val = left_rows[i]
            result.append([l_key, l_val, None])
            i += 1

    if how == "outer":
        while j < n_right:
            r_key, r_val = right_rows[j]
            result.append([r_key, None, r_val])
            j += 1

    return result
