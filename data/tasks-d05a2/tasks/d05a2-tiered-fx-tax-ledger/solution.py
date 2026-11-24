def _parse_minor(s: str) -> int:
    if not isinstance(s, str) or not s or s != s.strip() or s.startswith(("-", "+")):
        raise ValueError("Invalid amount string")
    parts = s.split(".")
    if len(parts) == 1:
        whole, frac = parts[0], "00"
    elif len(parts) == 2:
        whole, frac = parts[0], parts[1]
        if not (1 <= len(frac) <= 2):
            raise ValueError("Invalid decimal places")
        frac = frac.ljust(2, "0")
    else:
        raise ValueError("Invalid decimal format")
    if not whole.isdigit() or not frac.isdigit():
        raise ValueError("Amount must contain digits")
    return int(whole) * 100 + int(frac)


def _format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    val = abs(cents)
    return f"{sign}{val // 100}.{val % 100:02d}"


def _div_half_even(num: int, den: int) -> int:
    q, r = divmod(num, den)
    twice_r = 2 * r
    if twice_r > den:
        return q + 1
    if twice_r < den:
        return q
    return q + 1 if (q % 2 == 1) else q


def _validate_inputs(fx_rates: dict, brackets: list) -> None:
    if not isinstance(fx_rates, dict) or not fx_rates:
        raise ValueError("Invalid fx_rates")
    for cur, pair in fx_rates.items():
        if not isinstance(cur, str) or not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError("Invalid fx_rates entry")
        num, den = pair
        if (
            not isinstance(num, int) or isinstance(num, bool)
            or not isinstance(den, int) or isinstance(den, bool)
            or num <= 0 or den <= 0
        ):
            raise ValueError("FX rate numerator and denominator must be positive ints")

    if not isinstance(brackets, list) or not brackets:
        raise ValueError("Brackets must be non-empty")
    prev_cap = 0
    for idx, b in enumerate(brackets):
        if not isinstance(b, (list, tuple)) or len(b) != 2:
            raise ValueError("Invalid bracket")
        cap, rate = b
        if not isinstance(rate, int) or isinstance(rate, bool) or not (0 <= rate <= 10000):
            raise ValueError("Invalid bracket rate_bps")
        if cap is None:
            if idx != len(brackets) - 1:
                raise ValueError("Only the final bracket may have cap=None")
        else:
            if not isinstance(cap, int) or isinstance(cap, bool) or cap <= prev_cap:
                raise ValueError("Bracket caps must be strictly increasing positive integers")
            prev_cap = cap


def compute_fx_tax_summary(
    entries: list[dict],
    fx_rates: dict,
    brackets: list,
) -> dict:
    _validate_inputs(fx_rates, brackets)
    if not isinstance(entries, list):
        raise ValueError("entries must be a list")

    gross_cents = 0
    deduction_cents = 0
    for item in entries:
        cur = item.get("currency")
        amt_str = item.get("amount")
        kind = item.get("kind")
        if cur not in fx_rates or kind not in ("income", "deduction"):
            raise ValueError("Invalid entry currency or kind")
        minor = _parse_minor(amt_str)
        num, den = fx_rates[cur]
        usd_cents = _div_half_even(minor * num, den)
        if kind == "income":
            gross_cents += usd_cents
        else:
            deduction_cents += usd_cents

    taxable_cents = max(0, gross_cents - deduction_cents)
    tax_cents = 0
    for cap, rate in brackets:
        if taxable_cents <= 0:
            break
        slice_cents = taxable_cents if cap is None else min(taxable_cents, cap)
        tax_cents += _div_half_even(slice_cents * rate, 10000)
        if cap is not None and taxable_cents <= cap:
            break

    net_cents = taxable_cents - tax_cents
    return {
        "gross_usd": _format_cents(gross_cents),
        "deductions_usd": _format_cents(deduction_cents),
        "taxable_usd": _format_cents(taxable_cents),
        "tax_usd": _format_cents(tax_cents),
        "net_usd": _format_cents(net_cents),
    }
