# Double-Entry Ledger Book (`r07s1pkg`)

## Background
`r07s1pkg` implements an in-memory double-entry accounting ledger consisting of:
- `models.py`: Chart-of-accounts types (`AccountType`, `Account`), posting lines (`PostingLine`), journal entries (`JournalEntry`), and batch import validation (`parse_journal_entry`).
- `engine.py`: Stateful `LedgerBook` that registers accounts, validates and posts journal entries, tracks account balances, and produces trial balances and income statements.

## Reported Issues
Finance operations reported two defects during end-of-month closing:

1. **Multi-line split journal entries and decimal precision during entry parsing**:
   When parsing raw journal entry payloads via `parse_journal_entry(payload)`, entries with more than two lines or fractional cent rounding (or string/Decimal inputs) are being rejected or mis-validated. Specifically, `parse_journal_entry` must:
   - Require at least 2 posting lines (`len(lines) >= 2`), where every line has a strictly positive `amount > Decimal("0.00")` quantized to 2 decimal places (`0.01`, `ROUND_HALF_UP`) and `side` in `{"DEBIT", "CREDIT"}` (case-insensitive, normalized to uppercase `"DEBIT"` or `"CREDIT"`).
   - Reject entries where total debits do not equal total credits (`ValueError`), or where any single line has `amount <= 0` (`ValueError`).
   - Support split entries (3 or more lines across different or same accounts) as long as total debits equal total credits.

2. **Normal-balance calculation and period closing / income statement aggregation in `LedgerBook`**:
   - Each `AccountType` has a normal balance side:
     - Debit-normal (`"DEBIT"`): `AccountType.ASSET`, `AccountType.EXPENSE`
     - Credit-normal (`"CREDIT"`): `AccountType.LIABILITY`, `AccountType.EQUITY`, `AccountType.REVENUE`
   - `LedgerBook.get_balance(account_code, up_to_date=None)` must return the signed balance in the account's **normal balance direction**:
     - For debit-normal accounts: `total_debits - total_credits`
     - For credit-normal accounts: `total_credits - total_debits`
     - When `up_to_date` (an ISO `"YYYY-MM-DD"` string) is provided, only posted entries with `entry.date <= up_to_date` are included.
   - `LedgerBook.trial_balance(up_to_date=None)` returns a dictionary mapping `"total_debits"` and `"total_credits"` to the sum of net debit balances and net credit balances across all registered accounts, plus `"accounts"` mapping each `account_code` to `{"debit": Decimal, "credit": Decimal}`:
     - If an account's signed normal balance is positive, it appears on its normal side (`debit` for debit-normal, `credit` for credit-normal) and `0.00` on the opposite side.
     - If an account's signed normal balance is negative (contra/overdrawn balance), its absolute value `abs(balance)` must be placed on the **opposite** side so that `debit` and `credit` columns in the trial balance are always non-negative and `total_debits == total_credits`.
   - `LedgerBook.income_statement(start_date=None, end_date=None)` calculates `"revenue"`, `"expenses"`, and `"net_income"` (`revenue - expenses`) over posted entries filtered inclusively by `start_date <= entry.date <= end_date` (when each bound is provided).

## Specification Summary
- All monetary amounts use `decimal.Decimal` quantized to `Decimal("0.01")`.
- Posting an entry referencing an unregistered `account_code` or duplicate `entry_id` must raise `ValueError` without mutating ledger state.
