Fix `allocate_payout(total_str, recipients, fee_bps, round_mode)` in `solution.py`.

Implement an exact integer-cent payout allocator that deducts a platform fee in basis points (`1 bps = 1/10000`) and distributes the remaining net cents across recipients proportionally by integer weight using the Largest Remainder (Hamilton) method.

### Arguments
- `total_str`: A non-negative decimal money string with either no decimal point (whole dollars, e.g. `"25"`) or up to 2 decimal digits (e.g. `"25.5"`, `"25.50"`). Leading/trailing whitespace is not allowed. Raise `ValueError` if `total_str` is empty, negative, malformed, or has more than 2 decimal digits.
- `recipients`: A non-empty list of dicts `{"id": str, "weight": int}`.
  - Every `"id"` must be a non-empty string and unique across `recipients`.
  - Every `"weight"` must be a non-negative integer (`>= 0`), and the sum of all weights `W` across `recipients` must be strictly positive (`W > 0`).
  - Raise `ValueError` if `recipients` is empty, has duplicate or empty IDs, has any negative weight, or has total weight `W <= 0`.
- `fee_bps`: An integer between `0` and `10000` inclusive (`0 <= fee_bps <= 10000`). Raise `ValueError` otherwise.
- `round_mode`: Either `"half_even"` (banker's rounding) or `"half_up"` (round ties away from zero / toward positive infinity since amounts are non-negative). Raise `ValueError` for any other mode string.

### Exact Arithmetic Specification
1. **Parse Gross Cents**: Convert `total_str` into exact integer `gross_cents`.
2. **Fee Calculation**:
   - The unrounded fee in cents is `(gross_cents * fee_bps) / 10000`.
   - Let `q, r = divmod(gross_cents * fee_bps, 10000)`.
   - Round `q` using `r` against `10000`:
     - If `2 * r > 10000`, round up (`q + 1`).
     - If `2 * r < 10000`, round down (`q`).
     - If `2 * r == 10000`: round up (`q + 1`) if `round_mode == "half_up"`, or if `round_mode == "half_even"` and `q` is odd; otherwise keep `q`.
   - `net_cents = gross_cents - fee_cents`.
3. **Largest Remainder Allocation**:
   - Let `W` be the sum of all recipients' weights.
   - For each recipient `i` with weight `w_i`:
     - Exact share in cents is `(net_cents * w_i) / W`.
     - Base cents `base_i = (net_cents * w_i) // W`, and fractional numerator `rem_i = (net_cents * w_i) % W`.
   - Let `leftover = net_cents - sum(base_i)`. Distribute `1` extra cent to each of the top `leftover` recipients ranked by:
     1. Largest fractional remainder `rem_i` (descending),
     2. Largest integer weight `w_i` (descending),
     3. Lexicographically smallest recipient `"id"` (ascending, e.g. `"alice" < "bob"`).
4. **Return Value**:
   - Format all cent amounts as standard two-decimal strings `"D.CC"` (e.g. `0 -> "0.00"`, `5 -> "0.05"`, `1234 -> "12.34"`).
   - Return a dict:
     ```python
     {
         "gross": "<D.CC>",
         "fee": "<D.CC>",
         "net": "<D.CC>",
         "payouts": [{"id": "<id>", "amount": "<D.CC>"}, ...]
     }
     ```
   - The `"payouts"` list MUST preserve the original input order of `recipients`.

### Example
```python
allocate_payout(
    "10.00",
    [{"id": "b", "weight": 1}, {"id": "a", "weight": 1}, {"id": "c", "weight": 1}],
    0,
    "half_even",
)
# Returns:
# {
#   "gross": "10.00", "fee": "0.00", "net": "10.00",
#   "payouts": [
#     {"id": "b", "amount": "3.33"},
#     {"id": "a", "amount": "3.34"},
#     {"id": "c", "amount": "3.33"}
#   ]
# }
```
