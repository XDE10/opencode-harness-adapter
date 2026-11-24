# Issue Report: Reversal entries and period-filtered statement queries produce inaccurate balances

## Context
`r07s2pkg` implements an in-memory double-entry accounting ledger supporting chart-of-accounts registration, validated journal postings, reversal/void rollback entries, and period-scoped trial balance and income statement queries.

## Reported Symptoms
1. **Reversal entry generation and account balance updates**:
   When calling `LedgerEngine.void_entry(entry_id, reversal_id, period)` to roll back a posted journal entry, the generated reversal entry and the resulting account balances do not properly neutralize the original transaction. Specifically, calling `JournalEntry.build_reversal(...)` and posting it leaves accounts with doubled movements instead of offsetting the original debits and credits back to their pre-entry balances.
2. **Multi-step statement and trial-balance period queries after voiding or period filtering**:
   `LedgerEngine.trial_balance(up_to_period=...)` and `LedgerEngine.income_statement(period=...)` calculate balances by re-aggregating lines from stored entries. However:
   - `trial_balance(up_to_period)` currently returns live total account balances whenever `up_to_period` is passed, or when filtering entries by period it applies the wrong net-sign convention for credit-normal accounts (`LIABILITY`, `EQUITY`, `REVENUE`).
   - Every account's normal balance in `trial_balance(up_to_period=...)` must equal the sum of `account.signed_delta(line.debit, line.credit)` across all posted journal entries (including posted reversal entries) whose `entry.period <= up_to_period` (lexicographically, e.g. `"2025-01" <= "2025-02"`). Accounts with a zero balance must be omitted from the returned dictionary.

## Expected Specification
- **Account Types & Normal Balances (`AccountType`, `Account`)**:
  - Debit-normal accounts (`ASSET`, `EXPENSE`): `signed_delta(debit, credit)` is `debit - credit`.
  - Credit-normal accounts (`LIABILITY`, `EQUITY`, `REVENUE`): `signed_delta(debit, credit)` is `credit - debit`.
- **Journal Entries & Reversals (`JournalEntry`, `JournalLine`)**:
  - Every `JournalEntry` must have at least 2 lines, strictly non-negative integer amounts (in cents), positive total debits, and `total_debits == total_credits`.
  - `JournalEntry.build_reversal(reversal_id, period)` must create a new `JournalEntry` with `entry_id=reversal_id`, `period=period`, `description=f"REVERSAL of {self.entry_id}"`, `reverses_id=self.entry_id`, and lines where each original line's `debit` and `credit` amounts are swapped (`debit=line.credit, credit=line.debit`).
- **Void / Rollback Conflict Resolution (`LedgerEngine.void_entry`)**:
  - Raising `KeyError` if `entry_id` does not exist.
  - Raising `ValueError` if the target entry has already been voided (`entry.voided is True`) or is itself a reversal entry (`entry.reverses_id is not None`).
  - Otherwise marks the original entry `voided = True`, builds its reversal entry via `build_reversal(reversal_id, period)`, posts the reversal entry through the engine so live account balances and period history reflect the offsetting lines, and returns the posted reversal `JournalEntry`.
- **Period Queries (`trial_balance` and `income_statement`)**:
  - `trial_balance(up_to_period: str | None = None) -> dict[str, int]`: Returns `{account_code: normal_balance}` for all registered accounts with a non-zero normal balance as of `up_to_period` (or across all periods if `up_to_period is None`).
  - `income_statement(period: str | None = None) -> dict[str, int]`: Filters posted entries to `entry.period == period` (or all periods if `period is None`), returning `{"revenue": total_revenue, "expense": total_expense, "net_income": total_revenue - total_expense}` where revenue and expense are measured in their respective normal balance directions.
