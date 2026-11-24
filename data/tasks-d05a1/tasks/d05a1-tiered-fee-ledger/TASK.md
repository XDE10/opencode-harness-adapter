Fix `run_fee_ledger(brackets, ops)` in `solution.py`.

Implement a stateful billing cycle ledger that calculates progressive tiered fees (in integer basis points, where `10000 bps = 100%`) using banker's (round-half-to-even) cent rounding and remainder-fair cent splitting across recipients.

### Parameters
- `brackets`: Non-empty list of `[cap_cents, rate_bps]` pairs defining progressive volume tiers within a billing cycle:
  - Each `cap_cents` is either a positive integer (the cumulative cycle volume upper bound in cents for that tier) or `None` for the final unbounded tier.
  - Finite caps must be strictly increasing, and the last bracket must have `cap_cents = None`.
  - Every `rate_bps` must be an integer satisfying `0 <= rate_bps <= 10000`.
  - Raise `ValueError` if `brackets` is empty or violates any of these rules.
- `ops`: List of operation dicts executed sequentially. Track `cycle_volume` (integer cents, initially `0`) and a per-recipient map `balances` (string recipient ID -> integer cents, initially `0`).

### Operations
1. `{"op": "charge", "amount": int, "splits": list[dict]}`:
   - `amount` must be a positive integer (`> 0`).
   - `splits` must be a non-empty list of `{"recipient": str, "weight": int}` with unique `"recipient"` strings in the list and positive integer `"weight"` (`> 0`). Raise `ValueError` if `amount <= 0`, `splits` is empty, any weight `<= 0`, or duplicate recipients appear in `splits`.
   - **Progressive Fee**: The charge occupies the volume interval `[cycle_volume, cycle_volume + amount)`. For each bracket `[cap, rate_bps]` covering `[prev_cap, cap)` (where `prev_cap` starts at `0`), let `overlap` be the number of cents of this charge falling inside `[prev_cap, cap)`. Sum `overlap * rate_bps` across all brackets to get `total_numer`, then round `total_numer / 10000` to the nearest integer cent using **round-half-to-even** (banker's rounding: if `total_numer % 10000 == 5000`, round to the even integer cent). Advance `cycle_volume` by `amount`.
   - **Net Split**: Let `net = amount - fee`. Distribute `net` across `splits` proportionally to `"weight"` (let `W` be the sum of weights):
     - Each entry `i` gets base share `(net * w_i) // W` with exact remainder `rem_i = (net * w_i) % W`.
     - The leftover cents `R = net - sum(base_shares)` are distributed `1` cent each to the top `R` entries ordered by:
       1. Largest remainder `rem_i` descending,
       2. Largest weight `w_i` descending,
       3. Lexicographically smallest `"recipient"` string ascending.
   - Add each recipient's allocated net cents to `balances[recipient]`.
   - Append `{"fee": fee, "net": net, "allocations": {recipient: share, ...}}` (with all recipients from `splits`) to the result list.
2. `{"op": "refund", "amount": int}`:
   - `amount` must satisfy `0 < amount <= cycle_volume`; otherwise raise `ValueError`.
   - Reduce `cycle_volume` by `amount` and append `cycle_volume` to the result list.
3. `{"op": "close_cycle"}`:
   - Reset `cycle_volume` to `0` (recipient `balances` are preserved across cycles).
   - Append `{"balances": dict(sorted(balances.items()))}` to the result list.

### Example
```python
run_fee_ledger(
    [[1000, 200], [None, 100]],
    [
        {"op": "charge", "amount": 1000, "splits": [{"recipient": "b", "weight": 1}, {"recipient": "a", "weight": 1}]},
        {"op": "close_cycle"},
    ],
)
# Returns:
# [
#   {"fee": 20, "net": 980, "allocations": {"b": 490, "a": 490}},
#   {"balances": {"a": 490, "b": 490}}
# ]
```
