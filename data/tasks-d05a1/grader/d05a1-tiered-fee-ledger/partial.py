def _validate_brackets(brackets):
    if not brackets:
        raise ValueError("brackets must be non-empty")
    prev_cap = 0
    for idx, item in enumerate(brackets):
        if len(item) != 2:
            raise ValueError("invalid bracket")
        cap, rate = item
        if not isinstance(rate, int) or rate < 0 or rate > 10000:
            raise ValueError("invalid rate")
        if idx == len(brackets) - 1:
            if cap is not None:
                raise ValueError("last bracket must be unbounded")
        else:
            if not isinstance(cap, int) or cap <= prev_cap:
                raise ValueError("caps must be strictly increasing positive ints")
            prev_cap = cap


def _round_bps(numer):
    q, r = divmod(numer, 10000)
    if r > 5000 or (r == 5000 and q % 2 == 1):
        return q + 1
    return q


def _compute_progressive_fee(brackets, start_vol, amount):
    end_vol = start_vol + amount
    prev_cap = 0
    numer = 0
    for cap, rate in brackets:
        lo = max(start_vol, prev_cap)
        hi = end_vol if cap is None else min(end_vol, cap)
        if hi > lo:
            numer += (hi - lo) * rate
        if cap is not None:
            prev_cap = cap
    return _round_bps(numer)


def _split_net(net, splits):
    if not splits:
        raise ValueError("splits must be non-empty")
    seen = set()
    total_w = 0
    for s in splits:
        rec = s["recipient"]
        w = s["weight"]
        if rec in seen or not isinstance(w, int) or w <= 0:
            raise ValueError("invalid split entry")
        seen.add(rec)
        total_w += w

    items = []
    used = 0
    for idx, s in enumerate(splits):
        rec = s["recipient"]
        w = s["weight"]
        base, rem = divmod(net * w, total_w)
        used += base
        items.append([base, rem, w, idx, rec])

    leftover = net - used
    items.sort(key=lambda x: (-x[1], -x[2], x[3]))
    for i in range(leftover):
        items[i][0] += 1

    return {rec: share for share, _, _, _, rec in items}


def run_fee_ledger(brackets, ops):
    _validate_brackets(brackets)
    cycle_volume = 0
    balances = {}
    out = []
    for op in ops:
        kind = op["op"]
        if kind == "charge":
            amount = op["amount"]
            if not isinstance(amount, int) or amount <= 0:
                raise ValueError("amount must be positive")
            fee = _compute_progressive_fee(brackets, cycle_volume, amount)
            net = amount - fee
            allocs = _split_net(net, op["splits"])
            cycle_volume += amount
            for rec, share in allocs.items():
                balances[rec] = balances.get(rec, 0) + share
            out.append({"fee": fee, "net": net, "allocations": allocs})
        elif kind == "refund":
            amount = op["amount"]
            if not isinstance(amount, int) or amount <= 0 or amount > cycle_volume:
                raise ValueError("invalid refund amount")
            cycle_volume -= amount
            out.append(cycle_volume)
        elif kind == "close_cycle":
            cycle_volume = 0
            out.append({"balances": dict(sorted(balances.items()))})
        else:
            raise ValueError(f"unknown op: {kind}")
    return out
