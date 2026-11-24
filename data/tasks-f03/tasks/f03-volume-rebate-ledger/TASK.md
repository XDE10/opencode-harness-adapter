Fix `apply_volume_rebates(trades, schedule)` in `solution.py`.

Computes per-trade exchange fees and rebates using marginal monthly cumulative volume tiers per account.

### Inputs
- `trades` (`list[dict]`): ordered trade dicts, each with:
  - `id` (`str`): unique non-empty trade identifier.
  - `account` (`str`): non-empty account identifier.
  - `month` (`str`): non-empty billing month key (e.g. `"2026-03"`).
  - `notional_cents` (`int`): strictly positive integer trade notional (`> 0`).
  - `role` (`str`): `"maker"` or `"taker"`.
- `schedule` (`dict`):
  - `tiers` (`list[list]`): non-empty list of `[min_cum_cents, taker_bps, maker_bps]`. `min_cum_cents` values must be strictly increasing integers starting at `0`. `taker_bps` is an `int >= 0`; `maker_bps` is an `int` (may be negative for rebates).
  - `rebate_cap_cents` (`int | None`): optional non-negative integer cap on net rebate per `(account, month)`. If set, cumulative net fees in any `(account, month)` cannot drop below `-rebate_cap_cents`.

### Rules & Edge Cases
1. Validate all fields and schedule constraints; raise `ValueError` on invalid types (`bool`), duplicate trade `id`, `notional_cents <= 0`, unknown `role`, or invalid `tiers` / `rebate_cap_cents`.
2. Track cumulative volume independently per `(account, month)` starting at `0`.
3. A trade spanning `[start, start + notional_cents)` is split marginally across all overlapping tiers. Accumulate exact rational `slice_cents * bps / 10000` across the trade's slices, then round once to the nearest integer cent half-away-from-zero (e.g., `2.5 -> 3`, `-2.5 -> -3`).
4. If `rebate_cap_cents is not None` and `month_net_fee + fee_cents < -rebate_cap_cents`, clamp `fee_cents = -rebate_cap_cents - month_net_fee`.
5. Return `{"trades": [{"id": ..., "fee_cents": ...}, ...], "account_totals": {account: total_fee_cents, ...}}`.

### Example
```python
apply_volume_rebates(
    [{"id": "t1", "account": "A", "month": "2026-01", "notional_cents": 10000, "role": "maker"}],
    {"tiers": [[0, 20, -5]], "rebate_cap_cents": None},
)
# -> {"trades": [{"id": "t1", "fee_cents": -5}], "account_totals": {"A": -5}}
```
