# Double-Entry Ledger Book (`r07s3pkg`) — Issue Report & Behavioral Specification

## Problem Summary
Finance operations reported two classes of errors when importing batch journal entries and generating closing statements:
1. **Batch text parser (`parse_journal_batch`)**: Certain valid pipe-delimited journal lines with trailing/leading whitespace around account codes or lowercase direction tokens (`dr`/`cr`), as well as multi-line batches containing same-account split postings, are either rejected or have duplicate account legs collapsed during parsing.
2. **Stateful ledger posting & closing statements (`LedgerBook`)**: Contra-asset and credit-normal account balances and trial balance / income statement aggregations produce wrong signs or include post-cutoff transactions when an `as_of` date filter is supplied.

---

## Domain & Behavioral Specification

### 1. Chart of Accounts & Normal Balances (`r07s3pkg.models`)
- `AccountType` enum has five categories:
  -Debit-normal (`normal_side == "DR"`): `ASSET`, `EXPENSE`
  -Credit-normal (`normal_side == "CR"`): `LIABILITY`, `EQUITY`, `REVENUE`
- `Account(code: str, name: str, account_type: AccountType)`:
  - `normal_side` property returns `"DR"` for `ASSET` and `EXPENSE`, and `"CR"` for `LIABILITY`, `EQUITY`, and `REVENUE`.
  - `signed_delta(side: str, amount_cents: int) -> int`:
    - `side` must be `"DR"` or `"CR"` (case-insensitive, stripped).
    - `amount_cents` must be a strictly positive integer (`> 0`), otherwise raise `ValueError`.
    - Returns `+amount_cents` when `side` matches the account's `normal_side`, and `-amount_cents` when `side` opposes the account's `normal_side`.
- `PostingLeg(account_code: str, side: str, amount_cents: int, memo: str = "")`
- `JournalEntry(entry_id: str, posted_date: str, description: str, legs: tuple[PostingLeg, ...])`:
  - `posted_date` is an ISO date string `"YYYY-MM-DD"`.
  - A valid `JournalEntry` must have at least 2 legs, every leg must have `amount_cents > 0` and normalized `side in ("DR", "CR")`, and total `"DR"` cents across all legs must equal total `"CR"` cents (`ValueError` if unbalanced or invalid).
  - Multiple legs within the same `JournalEntry` **may reference the same `account_code`** (for example, split sub-items posted to the same expense or cash account in a single voucher). Every leg must be preserved in order.

### 2. Batch Journal Parser (`r07s3pkg.parser`)
- `parse_journal_batch(raw_text: str) -> list[JournalEntry]`
- Input format:
  - Blank lines and comment lines starting with `#` (after stripping whitespace) are ignored.
  - Entry header line starts with `@ENTRY` separated by pipes `|`:
    `@ENTRY | <entry_id> | <YYYY-MM-DD> | <description>`
  - Leg lines follow an `@ENTRY` header and have 3 or 4 pipe-separated fields:
    `<account_code> | <DR_or_CR> | <amount_dollars_or_cents> | [optional_memo]`
  - Whitespace around every field (`entry_id`, `posted_date`, `description`, `account_code`, `side`, `amount`, `memo`) must be stripped.
  - `side` is case-insensitive (`"dr"`, `"DR"`, `"Cr"`, etc.) and normalized to uppercase `"DR"` or `"CR"`.
  - Amount format (`parse_amount_cents(token: str) -> int`):
    - Accepts decimal dollar strings with an optional decimal point (up to 2 decimal places, e.g., `"125"`, `"125.5"`, `"125.50"` -> `12500`, `12550`, `12550` cents).
    - Must use exact integer/Decimal arithmetic (no float rounding bugs like `19.99 * 100 -> 1998`).
    - Negative or zero amounts, or more than 2 decimal places, raise `ValueError`.
  - Every leg belonging to an `@ENTRY` block must be preserved in `JournalEntry.legs` (do not overwrite or deduplicate legs that share an `account_code`), and each entry is validated before being returned.

### 3. Stateful Ledger Execution & Statements (`r07s3pkg.engine`)
- `LedgerBook`:
  - `register_account(account: Account) -> None`: registers an account by `account.code` (raises `ValueError` if `code` is already registered).
  - `post_entry(entry: JournalEntry) -> None`:
    - Validates the entry, checks that `entry.entry_id` has not already been posted (`ValueError` on duplicate `entry_id`), and verifies that every leg's `account_code` exists in the chart of accounts (`KeyError` if unknown).
    - Appends the entry to the ledger's chronological log.
  - `account_balance(account_code: str, as_of: str | None = None) -> int`:
    - Sums `account.signed_delta(leg.side, leg.amount_cents)` across all posted entries where `as_of is None or entry.posted_date <= as_of`.
    - Raises `KeyError` if `account_code` is unknown.
  - `trial_balance(as_of: str | None = None) -> dict[str, dict[str, int]]`:
    - For every registered account (sorted by `account.code`) that has a non-zero balance as of `as_of`, places the balance into `"debit_cents"` or `"credit_cents"` based on its normal side and sign:
      - Let `bal = self.account_balance(code, as_of=as_of)` (which is expressed in the account's normal-side direction).
      - Convert to raw net debit minus credit: for `"DR"` normal accounts, `net_dr = bal`; for `"CR"` normal accounts, `net_dr = -bal`.
      - If `net_dr > 0`, the row is `{"debit_cents": net_dr, "credit_cents": 0}`.
      - If `net_dr < 0`, the row is `{"debit_cents": 0, "credit_cents": -net_dr}`.
    - Also includes a `"TOTAL"` key mapping to `{"debit_cents": sum_debits, "credit_cents": sum_credits}` across all included accounts. In any valid double-entry ledger, `TOTAL["debit_cents"] == TOTAL["credit_cents"]` holds for any `as_of` cutoff date.
  - `income_statement(as_of: str | None = None) -> dict[str, int]`:
    - Computes as of `as_of` (inclusive: `entry.posted_date <= as_of`):
      - `"revenue_cents"`: sum of `account_balance(code, as_of=as_of)` for all `AccountType.REVENUE` accounts.
      - `"expense_cents"`: sum of `account_balance(code, as_of=as_of)` for all `AccountType.EXPENSE` accounts.
      - `"net_income_cents"`: `revenue_cents - expense_cents`.
