def _parse_cents(s: str) -> int:
    if not isinstance(s, str) or not s or s != s.strip() or s.startswith(("-", "+")):
        raise ValueError("Invalid amount string")
    parts = s.split(".")
    if len(parts) == 1:
        whole, frac = parts[0], "00"
    elif len(parts) == 2:
        whole, frac = parts[0], parts[1]
        if not (1 <= len(frac) <= 2):
            raise ValueError("Invalid fractional digits")
        frac = frac.ljust(2, "0")
    else:
        raise ValueError("Malformed decimal string")
    if not whole.isdigit() or not frac.isdigit():
        raise ValueError("Non-digit characters in amount")
    return int(whole) * 100 + int(frac)


def _format_cents(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def _div_round(num: int, den: int, mode: str) -> int:
    q, r = divmod(num, den)
    twice_r = 2 * r
    if twice_r > den:
        return q + 1
    if twice_r < den:
        return q
    if mode == "half_up":
        return q + 1
    if mode == "half_even":
        return q + 1 if (q % 2 == 0) else q
    raise ValueError(f"Unknown round_mode: {mode}")


def allocate_payout(
    total_str: str,
    recipients: list[dict],
    fee_bps: int,
    round_mode: str,
) -> dict:
    if round_mode not in ("half_even", "half_up"):
        raise ValueError("Invalid round_mode")
    if not isinstance(fee_bps, int) or isinstance(fee_bps, bool) or not (0 <= fee_bps <= 10000):
        raise ValueError("Invalid fee_bps")
    if not isinstance(recipients, list) or not recipients:
        raise ValueError("Recipients must be a non-empty list")

    gross_cents = _parse_cents(total_str)
    seen_ids = set()
    total_weight = 0
    for rec in recipients:
        rid = rec.get("id")
        w = rec.get("weight")
        if not isinstance(rid, str) or not rid or rid in seen_ids:
            raise ValueError("Invalid or duplicate recipient id")
        if not isinstance(w, int) or isinstance(w, bool) or w < 0:
            raise ValueError("Invalid recipient weight")
        seen_ids.add(rid)
        total_weight += w

    if total_weight <= 0:
        raise ValueError("Total weight must be positive")

    fee_cents = _div_round(gross_cents * fee_bps, 10000, round_mode)
    net_cents = gross_cents - fee_cents

    bases = []
    ranked = []
    for idx, rec in enumerate(recipients):
        w = rec["weight"]
        q, r = divmod(net_cents * w, total_weight)
        bases.append(q)
        ranked.append((-r, -w, rec["id"], idx))

    leftover = net_cents - sum(bases)
    ranked.sort()
    for k in range(leftover):
        _, _, _, idx = ranked[k]
        bases[idx] += 1

    payouts = [
        {"id": rec["id"], "amount": _format_cents(bases[idx])}
        for idx, rec in enumerate(recipients)
    ]
    return {
        "gross": _format_cents(gross_cents),
        "fee": _format_cents(fee_cents),
        "net": _format_cents(net_cents),
        "payouts": payouts,
    }
