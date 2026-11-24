def _valid_ccy(c):
    return isinstance(c, str) and len(c) == 3 and c.isalpha() and c.isupper()


def _round_rat(num, den, mode):
    if mode not in ("HALF_EVEN", "HALF_UP"):
        raise ValueError("invalid rounding mode")
    sign = -1 if num < 0 else 1
    num = abs(num)
    q, r = divmod(num, den)
    twice_r = 2 * r
    if twice_r > den:
        res = q + 1
    elif twice_r < den:
        res = q
    elif mode == "HALF_UP":
        res = q + 1
    else:
        res = q + 1 if (q % 2 == 1) else q
    return sign * res


def run_fx_ledger(base_currency, ops):
    if not _valid_ccy(base_currency):
        raise ValueError("invalid base currency")
    rates = {base_currency: (1, 1)}
    balances = {base_currency: 0}
    cost_basis = {}
    realized_pnl = 0
    out = []

    for op in ops:
        kind = op["op"]
        if kind == "set_rate":
            ccy = op["currency"]
            num, den = op["num"], op["den"]
            if not _valid_ccy(ccy) or ccy == base_currency:
                raise ValueError("invalid currency for set_rate")
            if not isinstance(num, int) or not isinstance(den, int) or num <= 0 or den <= 0:
                raise ValueError("rate must be positive ints")
            rates[ccy] = (num, den)
            out.append(None)

        elif kind == "deposit":
            ccy = op["currency"]
            amt = op["amount"]
            mode = op["rounding"]
            if not _valid_ccy(ccy) or ccy not in rates or not isinstance(amt, int) or amt <= 0:
                raise ValueError("invalid deposit")
            balances[ccy] = balances.get(ccy, 0) + amt
            if ccy != base_currency:
                num, den = rates[ccy]
                base_cost = _round_rat(amt * num, den, mode)
                cost_basis[ccy] = cost_basis.get(ccy, 0) + base_cost
            out.append(balances[ccy])

        elif kind == "convert":
            src = op["from"]
            dst = op["to"]
            amt = op["amount"]
            mode = op["rounding"]
            if (
                not _valid_ccy(src)
                or not _valid_ccy(dst)
                or src == dst
                or src not in rates
                or dst not in rates
                or not isinstance(amt, int)
                or amt <= 0
                or amt > balances.get(src, 0)
            ):
                raise ValueError("invalid convert")

            n_src, d_src = rates[src]
            n_dst, d_dst = rates[dst]
            base_val = _round_rat(amt * n_src, d_src, mode)
            to_amount = _round_rat(amt * n_src * d_dst, d_src * n_dst, mode)

            old_bal = balances[src]
            balances[src] = old_bal - amt
            if src != base_currency:
                old_basis = cost_basis.get(src, 0)
                if amt == old_bal:
                    removed = old_basis
                else:
                    removed = _round_rat(old_basis * amt, old_bal, mode)
                cost_basis[src] = old_basis - removed
                realized_pnl += base_val - removed

            balances[dst] = balances.get(dst, 0) + to_amount
            if dst != base_currency:
                cost_basis[dst] = cost_basis.get(dst, 0) + base_val

            out.append({
                "from_bal": balances[src],
                "to_amount": to_amount,
                "to_bal": balances[dst],
            })

        elif kind == "roll_period":
            mode = op["rounding"]
            for ccy, bal in sorted(balances.items()):
                if ccy != base_currency and bal > 0:
                    num, den = rates[ccy]
                    mkt_val = _round_rat(bal * num, den, mode)
                    realized_pnl += mkt_val - cost_basis.get(ccy, 0)
                    cost_basis[ccy] = mkt_val
            period_pnl = realized_pnl
            realized_pnl = 0
            total_nav = balances.get(base_currency, 0) + sum(
                cost_basis.get(c, 0) for c, b in balances.items() if c != base_currency and b > 0
            )
            out.append({"period_pnl": period_pnl, "total_nav": total_nav})

        else:
            raise ValueError(f"unknown op: {kind}")

    return out
