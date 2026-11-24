Fix `quote_fx_conversions(orders, fee_tiers)` in `solution.py`.

Quotes base-currency conversion amounts and tiered wire fees for FX orders using exact `Decimal` arithmetic.

### Inputs
- `orders` (`list[dict]`): each order has:
  - `id` (`str`): unique non-empty identifier.
  - `foreign_amount` (`str`): positive decimal string amount of foreign currency.
  - `rate` (`str`): positive decimal string FX rate (base currency units per 1 foreign unit).
  - `side` (`str`): `"BUY"` (buying foreign currency, paying base) or `"SELL"` (selling foreign currency, receiving base).
  - `spread_bps` (`int`): non-negative integer spread in basis points.
- `fee_tiers` (`list[dict]`): non-empty list of cliff tiers `{"up_to_cents": int | None, "bps": int, "flat_cents": int}` sorted strictly ascending by `up_to_cents` (`None` allowed only on the final tier), with `bps >= 0` and `flat_cents >= 0`.

### Rules & Edge Cases
1. Validate all fields; raise `ValueError` on duplicate/empty `id`, non-positive `foreign_amount` or `rate`, invalid decimal strings, `spread_bps < 0`, invalid `side`, or invalid `fee_tiers`.
2. Effective rate:
   - `"BUY"`: `rate * (10000 + spread_bps) / 10000`
   - `"SELL"`: `rate * (10000 - spread_bps) / 10000` (must be `> 0`, else `ValueError`).
3. `gross_base_cents` = exact `foreign_amount * effective_rate * 100`, rounded `ROUND_HALF_UP` to integer cents.
4. Select the first tier where `up_to_cents is None or gross_base_cents <= up_to_cents` (raise `ValueError` if no tier covers `gross_base_cents`).
5. `fee_cents = flat_cents + round_half_up(gross_base_cents * bps / 10000)`.
6. For `"BUY"`, `net_base_cents = gross_base_cents + fee_cents`. For `"SELL"`, `net_base_cents = gross_base_cents - fee_cents` (must be `>= 0`, else `ValueError`).
7. Return `[{"id": str, "gross_base_cents": int, "fee_cents": int, "net_base_cents": int}, ...]`.

### Example
```python
quote_fx_conversions(
    [{"id": "q1", "foreign_amount": "100.00", "rate": "1.20", "side": "BUY", "spread_bps": 50}],
    [{"up_to_cents": None, "bps": 100, "flat_cents": 200}],
)
# -> [{"id": "q1", "gross_base_cents": 12060, "fee_cents": 321, "net_base_cents": 12381}]
```
