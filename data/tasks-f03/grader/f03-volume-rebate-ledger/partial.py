from fractions import Fraction


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_schedule(schedule):
    if not isinstance(schedule, dict) or "tiers" not in schedule:
        raise ValueError("schedule must be a dict with tiers")
    tiers = schedule["tiers"]
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("tiers must be non-empty")
    parsed = []
    prev_min = None
    for row in tiers:
        if not isinstance(row, (list, tuple)) or len(row) != 3:
            raise ValueError("tier row must be [min_cum_cents, taker_bps, maker_bps]")
        min_cum, taker_bps, maker_bps = row
        if not (_is_int(min_cum) and _is_int(taker_bps) and _is_int(maker_bps)):
            raise ValueError("tier values must be integers")
        if taker_bps < 0:
            raise ValueError("taker_bps must be non-negative")
        if prev_min is None:
            if min_cum != 0:
                raise ValueError("first tier must start at 0")
        elif min_cum <= prev_min:
            raise ValueError("tier thresholds must strictly increase")
        prev_min = min_cum
        parsed.append((min_cum, taker_bps, maker_bps))
    cap = schedule.get("rebate_cap_cents")
    if cap is not None and (not _is_int(cap) or cap < 0):
        raise ValueError("rebate_cap_cents must be non-negative int or None")
    return parsed, cap


def _trade_exact_fee(start, end, tiers, is_maker):
    total = Fraction(0)
    for idx, (tier_min, taker_bps, maker_bps) in enumerate(tiers):
        next_min = tiers[idx + 1][0] if idx + 1 < len(tiers) else None
        lo = max(start, tier_min)
        hi = end if next_min is None else min(end, next_min)
        if hi > lo:
            bps = maker_bps if is_maker else taker_bps
            total += Fraction((hi - lo) * bps, 10000)
    return total


def apply_volume_rebates(trades, schedule):
    tiers, rebate_cap = _validate_schedule(schedule)
    if not isinstance(trades, list):
        raise ValueError("trades must be a list")
    seen_ids = set()
    cum_volume = {}
    month_fees = {}
    account_totals = {}
    results = []

    for trade in trades:
        tid = trade.get("id")
        acct = trade.get("account")
        month = trade.get("month")
        notional = trade.get("notional_cents")
        role = trade.get("role")
        if not tid or not acct or not month or tid in seen_ids:
            raise ValueError("invalid or duplicate trade identifiers")
        if not _is_int(notional) or notional <= 0 or role not in ("maker", "taker"):
            raise ValueError("invalid notional_cents or role")
        seen_ids.add(tid)

        key = (acct, month)
        start = cum_volume.get(key, 0)
        end = start + notional
        exact = _trade_exact_fee(start, end, tiers, role == "maker")
        fee_cents = int(exact)

        prev_fee = month_fees.get(key, 0)
        if rebate_cap is not None and prev_fee + fee_cents < -rebate_cap:
            fee_cents = -rebate_cap - prev_fee

        cum_volume[key] = end
        month_fees[key] = prev_fee + fee_cents
        account_totals[acct] = account_totals.get(acct, 0) + fee_cents
        results.append({"id": tid, "fee_cents": fee_cents})

    return {"trades": results, "account_totals": account_totals}
