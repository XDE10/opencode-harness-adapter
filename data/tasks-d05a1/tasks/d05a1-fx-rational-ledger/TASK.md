Fix `run_fx_ledger(base_currency, ops)` in `solution.py`.

Implement a multi-currency ledger that tracks integer minor-unit balances (e.g., cents), exact rational FX rates (`num / den`), and realized FX PnL in `base_currency` across period rollovers.

### State & Rules
- `base_currency`: A 3-letter uppercase ASCII currency code (e.g. `"USD"`). Raise `ValueError` if not a 3-letter uppercase ASCII string.
- Every currency code in `ops` must also be a 3-letter uppercase ASCII string (`len(c) == 3 and c.isalpha() and c.isupper()`).
- **FX Rates**:
  - `base_currency` always has an implicit exact rate of `1 / 1` (`num = 1, den = 1`).
  - For any currency `C`, its rate `(num, den)` represents how many units of `base_currency` equal `1` unit of `C` (`value_in_base = amount_in_C * num / den`).
- **Rounding Modes**:
  - `"HALF_EVEN"`: round to nearest integer; exact half-way cases (`2 * remainder == denominator`) round to the nearest **even** integer.
  - `"HALF_UP"`: round to nearest integer; exact half-way cases round **away from zero** (e.g., `+2.5 -> +3`, `-2.5 -> -3`).
  - Raise `ValueError` on any other rounding mode string.
- **Cost Basis & Realized PnL**:
  - For each non-base currency `C`, track both `balance[C]` (integer minor units, initially `0`, never allowed to go negative) and `cost_basis[C]` (integer minor units in `base_currency`, initially `0`).
  - Also track `realized_pnl` (integer minor units in `base_currency`, initially `0` for the current period).

### Operations
1. `{"op": "set_rate", "currency": str, "num": int, "den": int}`:
   - Set the FX rate for `currency` to `num / den`.
   - Raise `ValueError` if `currency == base_currency`, if `currency` is invalid, or if `num <= 0` or `den <= 0`.
   - Append `None` to results.
2. `{"op": "deposit", "currency": str, "amount": int, "rounding": str}`:
   - `amount` must be a positive integer (`> 0`). The currency must have a defined rate (or be `base_currency`).
   - Increase `balance[currency]` by `amount`.
   - If `currency != base_currency`, compute `base_cost = round(amount * num / den, rounding)` and add `base_cost` to `cost_basis[currency]`.
   - Append `balance[currency]` to results.
3. `{"op": "convert", "from": str, "to": str, "amount": int, "rounding": str}`:
   - `from` and `to` must be valid, distinct currencies (`from != to`), both with defined rates, and `0 < amount <= balance[from]`; otherwise raise `ValueError`.
   - Let `(num_from, den_from)` and `(num_to, den_to)` be the exact rates of `from` and `to`.
   - Compute `to_amount = round(amount * num_from * den_to / (den_from * num_to), rounding)` using exact single-step rational arithmetic (do NOT round an intermediate base amount first).
   - Compute `base_val = round(amount * num_from / den_from, rounding)`.
   - Update `from`:
     - Let `old_bal = balance[from]`. Decrease `balance[from]` by `amount`.
     - If `from != base_currency`: the removed cost basis is `basis_removed = cost_basis[from]` if `amount == old_bal` else `round(cost_basis[from] * amount / old_bal, rounding)`. Decrease `cost_basis[from]` by `basis_removed` and add `base_val - basis_removed` to `realized_pnl`.
   - Update `to`:
     - Increase `balance[to]` by `to_amount`.
     - If `to != base_currency`, increase `cost_basis[to]` by `base_val`.
   - Append `{"from_bal": balance[from], "to_amount": to_amount, "to_bal": balance[to]}` to results.
4. `{"op": "roll_period", "rounding": str}`:
   - Re-mark all held non-base currencies with `balance[C] > 0` to market at their current FX rate:
     - For each non-base `C` with `balance[C] > 0`, let `mkt_val = round(balance[C] * num_C / den_C, rounding)`.
     - Add `mkt_val - cost_basis[C]` to `realized_pnl`, and set `cost_basis[C] = mkt_val`.
   - Snapshot `period_pnl = realized_pnl`, reset `realized_pnl = 0` for the new period, and compute `total_nav = balance[base_currency] + sum(cost_basis[C] for all non-base C with balance[C] > 0)`.
   - Append `{"period_pnl": period_pnl, "total_nav": total_nav}` to results.

### Example
```python
run_fx_ledger("USD", [
    {"op": "set_rate", "currency": "EUR", "num": 11, "den": 10},
    {"op": "deposit", "currency": "EUR", "amount": 100, "rounding": "HALF_EVEN"},
    {"op": "set_rate", "currency": "EUR", "num": 12, "den": 10},
    {"op": "roll_period", "rounding": "HALF_EVEN"},
])
# Returns: [None, 100, None, {"period_pnl": 10, "total_nav": 120}]
```
