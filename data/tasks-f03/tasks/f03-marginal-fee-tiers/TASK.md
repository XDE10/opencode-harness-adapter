Fix `compute_tiered_fee(amount_cents, tiers, min_fee_cents=0, max_fee_cents=None)` in `solution.py`.

Computes a progressive (marginal bracket) transaction fee in integer cents.

### Inputs
- `amount_cents` (`int`): non-negative integer transaction amount in cents. Must not be a `bool`.
- `tiers` (`list[list]`): non-empty list of `[up_to_cents, bps]` pairs:
  - `up_to_cents` is a positive `int` or `None` (unbounded top tier). Upper bounds must be strictly increasing, and `None` may appear only as the final tier.
  - `bps` is a non-negative `int` (basis points, where `10000` bps = `100%`).
- `min_fee_cents` (`int`, default `0`): non-negative integer minimum fee.
- `max_fee_cents` (`int | None`, default `None`): optional non-negative integer maximum fee. If provided, must satisfy `max_fee_cents >= min_fee_cents`.

### Rules & Edge Cases
1. Validate all inputs; raise `ValueError` for invalid types (`bool`), negative values, empty `tiers`, non-increasing tier bounds, `None` in a non-final tier, `max_fee_cents < min_fee_cents`, or if `amount_cents` exceeds the highest finite tier when no unbounded (`None`) tier exists.
2. If `amount_cents == 0`, return `{"fee_cents": 0, "raw_fee_cents": 0, "breakdown": []}` immediately (`min_fee_cents` is not charged on zero-amount transactions).
3. Otherwise, split `amount_cents` marginally across tiers starting from `0`. For each tier with positive `slice_cents`, record `{"tier_index": i, "slice_cents": slice_cents, "bps": bps}` in `breakdown`.
4. Accumulate exact rational fees `slice_cents * bps / 10000` across all slices, then round once to the nearest cent using half-up (`0.5` rounds up) to obtain `raw_fee_cents`.
5. Clamp `raw_fee_cents` to `[min_fee_cents, max_fee_cents]` (if `max_fee_cents is not None`) to obtain `fee_cents`.

### Example
```python
compute_tiered_fee(100000, [[50000, 100], [None, 200]])
# -> {
#   "fee_cents": 1500,
#   "raw_fee_cents": 1500,
#   "breakdown": [
#     {"tier_index": 0, "slice_cents": 50000, "bps": 100},
#     {"tier_index": 1, "slice_cents": 50000, "bps": 200},
#   ],
# }
```
