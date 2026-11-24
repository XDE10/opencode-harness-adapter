from fractions import Fraction


def _is_valid_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _round_half_up_nonneg(frac):
    num, den = frac.numerator, frac.denominator
    return (num * 2 + den) // (2 * den)


def _validate_tiers(tiers):
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("tiers must be a non-empty list")
    prev_bound = 0
    seen_unbounded = False
    parsed = []
    for entry in tiers:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ValueError("each tier must have [up_to_cents, bps]")
        up_to, bps = entry
        if seen_unbounded:
            raise ValueError("unbounded tier must be last")
        if not _is_valid_int(bps) or bps < 0:
            raise ValueError("bps must be a non-negative integer")
        if up_to is None:
            seen_unbounded = True
        else:
            if not _is_valid_int(up_to) or up_to <= prev_bound:
                raise ValueError("tier upper bounds must be strictly increasing positive ints")
            prev_bound = up_to
        parsed.append((up_to, bps))
    return parsed


def compute_tiered_fee(amount_cents, tiers, min_fee_cents=0, max_fee_cents=None):
    if not _is_valid_int(amount_cents) or amount_cents < 0:
        raise ValueError("amount_cents must be a non-negative integer")
    if not _is_valid_int(min_fee_cents) or min_fee_cents < 0:
        raise ValueError("min_fee_cents must be a non-negative integer")
    if max_fee_cents is not None:
        if not _is_valid_int(max_fee_cents) or max_fee_cents < 0:
            raise ValueError("max_fee_cents must be a non-negative integer or None")
        if max_fee_cents < min_fee_cents:
            raise ValueError("max_fee_cents cannot be less than min_fee_cents")

    parsed_tiers = _validate_tiers(tiers)
    if amount_cents == 0:
        return {"fee_cents": 0, "raw_fee_cents": 0, "breakdown": []}

    prev = 0
    exact_fee = Fraction(0)
    breakdown = []
    for idx, (up_to, bps) in enumerate(parsed_tiers):
        if prev >= amount_cents:
            break
        cap = amount_cents if up_to is None else min(amount_cents, up_to)
        slice_cents = cap - prev
        if slice_cents > 0:
            exact_fee += Fraction(slice_cents * bps, 10000)
            breakdown.append({
                "tier_index": idx,
                "slice_cents": slice_cents,
                "bps": bps,
            })
        prev = cap

    if prev < amount_cents:
        raise ValueError("amount_cents exceeds highest finite tier")

    raw_fee_cents = _round_half_up_nonneg(exact_fee)
    fee_cents = max(min_fee_cents, raw_fee_cents)
    if max_fee_cents is not None:
        fee_cents = min(max_fee_cents, fee_cents)

    return {
        "fee_cents": fee_cents,
        "raw_fee_cents": raw_fee_cents,
        "breakdown": breakdown,
    }
