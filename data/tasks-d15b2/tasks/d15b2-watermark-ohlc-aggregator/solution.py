def _is_int(x):
    return type(x) is int


def _make_bar(bar_index, rows):
    first = rows[0]
    last = rows[-1]
    prices = [row[3] for row in rows]
    return {
        "bar": bar_index,
        "open": first[3],
        "high": max(prices),
        "low": min(prices),
        "close": last[3],
        "volume": len(rows),
        "first_seq": first[1],
        "last_seq": last[1],
    }


def _emit(bars, bucket, lateness, watermark, out):
    limit = watermark - lateness
    for bar_index in sorted(bars):
        close = (bar_index + 1) * bucket
        if close < limit:
            out.append(_make_bar(bar_index, bars.pop(bar_index)))


def _emit_all(bars, out):
    for bar_index in sorted(bars):
        out.append(_make_bar(bar_index, bars.pop(bar_index)))


def _check_config(op):
    return (
        isinstance(op, dict)
        and set(op) == {"op", "bucket", "lateness"}
        and op["op"] == "config"
        and _is_int(op["bucket"])
        and _is_int(op["lateness"])
        and op["bucket"] >= 1
        and op["lateness"] >= 0
    )


def run(ops):
    if not isinstance(ops, list):
        raise TypeError
    if not ops or not _check_config(ops[0]):
        raise ValueError
    bucket = ops[0]["bucket"]
    lateness = ops[0]["lateness"]
    watermark = None
    bars = {}
    out = []
    ended = False
    for pos, op in enumerate(ops[1:], 1):
        if ended or not isinstance(op, dict):
            raise ValueError
        kind = op.get("op")
        if kind == "event":
            if set(op) != {"op", "t", "price", "seq"} or any(
                not _is_int(op[key]) for key in ("t", "price", "seq")
            ):
                raise ValueError
            t, price, seq = op["t"], op["price"], op["seq"]
            if watermark is not None and t < watermark - lateness:
                continue
            bars.setdefault(t // bucket, []).append((t, seq, pos, price))
        elif kind == "watermark":
            if set(op) != {"op", "t"} or not _is_int(op["t"]):
                raise ValueError
            t = op["t"]
            watermark = t if watermark is None else max(watermark, t)
            _emit(bars, bucket, lateness, watermark, out)
        elif kind == "end":
            if set(op) != {"op"}:
                raise ValueError
            ended = True
            _emit_all(bars, out)
        else:
            raise ValueError
    return out
