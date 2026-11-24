Fix `compute_fx_tax_summary(entries, fx_rates, brackets)` in `solution.py`.

Implement an exact rational FX conversion and progressive marginal tax calculator for multi-currency income and deduction entries.

### Arguments
1. `entries`: A list of dicts `{"currency": str, "amount": str, "kind": str}` (may be empty).
   - `"currency"`: Currency code string that must exist in `fx_rates`. Raise `ValueError` if unknown.
   - `"amount"`: Unsigned non-negative decimal string with 0 to 2 fractional digits (e.g. `"100"`, `"100.5"`, `"100.50"`). No leading/trailing whitespace or signs (`+`/`-`). Raise `ValueError` if invalid.
   - `"kind"`: Either `"income"` or `"deduction"`. Raise `ValueError` for any other string.
2. `fx_rates`: A dict mapping currency codes to `[numerator, denominator]` integer pairs representing the exact conversion factor to USD (`1 unit of currency = numerator / denominator USD`).
   - Both `numerator` and `denominator` must be positive integers (`> 0`). Raise `ValueError` if `fx_rates` is not a dict or any entry in `fx_rates` violates this.
3. `brackets`: A non-empty list of `[cap_cents, rate_bps]` pairs defining progressive marginal tax tiers in USD cents:
   - `cap_cents` is either a positive integer (`> 0`) representing the cumulative upper bound of that bracket in USD cents, or `None` for the final unbounded top bracket.
   - All non-`None` `cap_cents` must be strictly increasing, and ONLY the last bracket may have `cap_cents is None`.
   - `rate_bps` is an integer in `0 <= rate_bps <= 10000` (`1 bps = 1/10000`).
   - Raise `ValueError` if `brackets` is empty or violates any bracket rule.

### Calculation Rules
1. **Per-Entry USD Conversion (Half-Even Rounding)**:
   - Parse `"amount"` into minor units (`minor = whole * 100 + frac`, so `"1.00"` is `100` minor units).
   - Convert to USD cents using the currency's `[num, den]` rate: exact USD cents is `(minor * num) / den`.
   - Round `(minor * num) / den` to the nearest integer cent using **banker's rounding (round half to even)** before summing:
     - Let `q, r = divmod(minor * num, den)`.
     - If `2 * r > den`, round to `q + 1`.
     - If `2 * r < den`, round to `q`.
     - If `2 * r == den`, round to `q + 1` if `q` is odd, else `q`.
2. **Gross, Deductions, and Taxable USD Cents**:
   - `gross_cents` = sum of converted USD cents for all `"income"` entries.
   - `deduction_cents` = sum of converted USD cents for all `"deduction"` entries.
   - `taxable_cents = max(0, gross_cents - deduction_cents)`.
3. **Progressive Marginal Tax Calculation**:
   - Let `prev_cap = 0`. Iterate through `brackets` in order `(cap_cents, rate_bps)`:
     - If `taxable_cents <= prev_cap`, the taxable amount in this bracket is `0`.
     - Otherwise, the taxable slice in this bracket is `slice_cents = taxable_cents - prev_cap` if `cap_cents is None` else `min(taxable_cents, cap_cents) - prev_cap`.
     - Compute the tax for **each bracket independently** as `(slice_cents * rate_bps) / 10000` rounded to integer cents via **banker's rounding (half to even)**, then sum the rounded bracket taxes to obtain `tax_cents`.
     - If `cap_cents is not None`, update `prev_cap = cap_cents`.
   - `net_cents = gross_cents - deduction_cents - tax_cents`. Note that `net_cents` can be negative if `deduction_cents > gross_cents`; format negative cents with a leading `"-"` (e.g. `-250 -> "-2.50"`).

### Return Value
Return a dict with 5 formatted `"D.CC"` (or `"-D.CC"`) strings:
```python
{
    "gross_usd": "<D.CC>",
    "deductions_usd": "<D.CC>",
    "taxable_usd": "<D.CC>",
    "tax_usd": "<D.CC>",
    "net_usd": "<D.CC>"
}
```

### Example
```python
compute_fx_tax_summary(
    [{"currency": "USD", "amount": "150.00", "kind": "income"}],
    {"USD": [1, 1]},
    [[10000, 1000], [None, 2000]],
)
# First $100.00 (10000c) taxed at 10% (1000 bps) = $10.00
# Next $50.00 (5000c) taxed at 20% (2000 bps) = $10.00
# Returns:
# {
#   "gross_usd": "150.00", "deductions_usd": "0.00",
#   "taxable_usd": "150.00", "tax_usd": "20.00", "net_usd": "130.00"
# }
```
