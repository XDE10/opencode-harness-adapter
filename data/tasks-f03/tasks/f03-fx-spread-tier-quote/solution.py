from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_tiers(fee_tiers):
    if not isinstance(fee_tiers, list) or not fee_tiers:
        raise ValueError("fee_tiers must be non-empty")
    prev = 0
    seen_none = False
    parsed = []
    for tier in fee_tiers:
        if seen_none:
            raise ValueError("unbounded tier must be last")
        up_to = tier.get("up_to_cents")
        bps = tier.get("bps")
        flat = tier.get("flat_cents")
        if not _is_int(bps) or bps < 0 or not _is_int(flat) or flat < 0:
            raise ValueError("bps and flat_cents must be non-negative ints")
        if up_to is None:
            seen_none = True
        else:
            if not _is_int(up_to) or up_to <= prev:
                raise ValueError("up_to_cents must be strictly increasing positive ints")
            prev = up_to
        parsed.append((up_to, bps, flat))
    return parsed


def _select_tier(gross_cents, tiers):
    for up_to, bps, flat in tiers:
        if up_to is None or gross_cents < up_to:
            return bps, flat
    raise ValueError("gross_base_cents exceeds all fee tiers")


def _round_half_up_dec(val):
    return int(val.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def quote_fx_conversions(orders, fee_tiers):
    tiers = _validate_tiers(fee_tiers)
    if not isinstance(orders, list):
        raise ValueError("orders must be a list")
    seen = set()
    quotes = []
    for order in orders:
        oid = order.get("id")
        side = order.get("side")
        spread = order.get("spread_bps")
        if not oid or oid in seen or side not in ("BUY", "SELL") or not _is_int(spread) or spread < 0:
            raise ValueError("invalid order metadata")
        seen.add(oid)
        try:
            amt = float(order["foreign_amount"])
            rate = float(order["rate"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("invalid numeric string")
        if amt <= 0 or rate <= 0:
            raise ValueError("amount and rate must be positive")
        mult = (10000 + spread) / 10000 if side == "BUY" else (10000 - spread) / 10000
        if mult <= 0:
            raise ValueError("effective rate must be positive")
        gross_cents = round(amt * rate * mult * 100)
        bps, flat = _select_tier(gross_cents, tiers)
        fee_cents = flat + _round_half_up_dec(Decimal(gross_cents) * Decimal(bps) / Decimal(10000))
        net_cents = gross_cents + fee_cents if side == "BUY" else gross_cents - fee_cents
        quotes.append({
            "id": oid,
            "gross_base_cents": gross_cents,
            "fee_cents": fee_cents,
            "net_base_cents": net_cents,
        })
    return quotes
