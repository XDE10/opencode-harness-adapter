import pytest
from r07s3pkg import (
    Account,
    AccountType,
    JournalEntry,
    LedgerBook,
    PostingLeg,
    parse_amount_cents,
    parse_journal_batch,
)


def make_standard_book() -> LedgerBook:
    book = LedgerBook()
    book.register_account(Account("1010", "Operating Cash", AccountType.ASSET))
    book.register_account(Account("1200", "Accounts Receivable", AccountType.ASSET))
    book.register_account(Account("2010", "Accounts Payable", AccountType.LIABILITY))
    book.register_account(Account("3010", "Owner Equity", AccountType.EQUITY))
    book.register_account(Account("4010", "SaaS Revenue", AccountType.REVENUE))
    book.register_account(Account("5010", "Cloud Hosting Expense", AccountType.EXPENSE))
    book.register_account(Account("5020", "Office Supplies Expense", AccountType.EXPENSE))
    return book


def test_account_normal_side_and_signed_delta():
    asset = Account("1010", "Cash", AccountType.ASSET)
    rev = Account("4010", "Revenue", AccountType.REVENUE)
    assert asset.normal_side == "DR"
    assert rev.normal_side == "CR"
    assert asset.signed_delta("dr", 500) == 500
    assert asset.signed_delta("CR", 200) == -200
    assert rev.signed_delta("CR", 750) == 750
    assert rev.signed_delta("DR", 150) == -150


def test_amount_parsing_validation():
    assert parse_amount_cents("0.01") == 1
    assert parse_amount_cents("19.99") == 1999
    assert parse_amount_cents("100.5") == 10050
    with pytest.raises(ValueError):
        parse_amount_cents("0")
    with pytest.raises(ValueError):
        parse_amount_cents("-10.00")
    with pytest.raises(ValueError):
        parse_amount_cents("12.345")


def test_unbalanced_entry_and_duplicate_entry_rejected():
    with pytest.raises(ValueError):
        JournalEntry(
            entry_id="BAD-1",
            posted_date="2025-02-01",
            description="Unbalanced",
            legs=(
                PostingLeg("1010", "DR", 1000),
                PostingLeg("4010", "CR", 900),
            ),
        )

    book = make_standard_book()
    entry = JournalEntry(
        entry_id="OK-1",
        posted_date="2025-02-01",
        description="Balanced",
        legs=(
            PostingLeg("1010", "DR", 1000),
            PostingLeg("4010", "CR", 1000),
        ),
    )
    book.post_entry(entry)
    with pytest.raises(ValueError):
        book.post_entry(entry)


def test_overdrawn_asset_Flips_to_credit_column_in_trial_balance():
    book = make_standard_book()
    book.post_entry(
        JournalEntry(
            entry_id="E-1",
            posted_date="2025-01-10",
            description="Overdraft cash for hosting",
            legs=(
                PostingLeg("5010", "DR", 30000),
                PostingLeg("1010", "CR", 30000),
            ),
        )
    )
    assert book.account_balance("1010") == -30000
    tb = book.trial_balance()
    assert tb["1010"] == {"debit_cents": 0, "credit_cents": 30000}
    assert tb["5010"] == {"debit_cents": 30000, "credit_cents": 0}
    assert tb["TOTAL"] == {"debit_cents": 30000, "credit_cents": 30000}


def test_parse_batch_preserves_multiple_legs_for_same_account():
    raw = """
    # Split expense voucher where two legs hit the same expense account 5010
    @ENTRY | V-101 | 2025-03-05 | Split AWS bills paid from cash
    5010 | dr | 120.00 | Prod cluster
    5010 | dr | 80.50  | Staging cluster
    1010 | cr | 200.50 | Combined wire
    """
    entries = parse_journal_batch(raw)
    assert len(entries) == 1
    assert len(entries[0].legs) == 3
    assert [leg.amount_cents for leg in entries[0].legs] == [12000, 8050, 20050]
    assert [leg.memo for leg in entries[0].legs] == [
        "Prod cluster",
        "Staging cluster",
        "Combined wire",
    ]


def test_posting_parsed_split_entry_accumulates_all_same_account_legs():
    book = make_standard_book()
    raw = """
    @ENTRY | V-202 | 2025-03-10 | Multi-invoice customer cash receipt
    1010 | DR | 150.00 | Check #101
    1010 | DR | 250.00 | Check #102
    4010 | CR | 400.00 | March SaaS subscriptions
    """
    for entry in parse_journal_batch(raw):
        book.post_entry(entry)

    assert book.account_balance("1010") == 40000
    assert book.account_balance("4010") == 40000
    assert book.income_statement()["net_income_cents"] == 40000


def test_account_balance_as_of_cutoff_excludes_future_entries():
    book = make_standard_book()
    raw = """
    @ENTRY | J-10 | 2025-01-10 | Seed investment
    1010 | DR | 1000.00
    3010 | CR | 1000.00

    @ENTRY | J-20 | 2025-01-20 | Mid-month revenue
    1010 | DR | 300.00
    4010 | CR | 300.00

    @ENTRY | J-30 | 2025-01-31 | Month-end hosting bill
    5010 | DR | 125.00
    1010 | CR | 125.00
    """
    for entry in parse_journal_batch(raw):
        book.post_entry(entry)

    assert book.account_balance("1010", as_of="2025-01-15") == 100000
    assert book.account_balance("1010", as_of="2025-01-20") == 130000
    assert book.account_balance("1010", as_of="2025-01-31") == 117500
    assert book.account_balance("1010", as_of="2025-01-01") == 0


def test_trial_balance_and_income_statement_respect_as_of_date():
    book = make_standard_book()
    raw = """
    @ENTRY | Q1-1 | 2025-01-15 | January subscription revenue
    1200 | DR | 500.00
    4010 | CR | 500.00

    @ENTRY | Q1-2 | 2025-01-25 | January cloud expense
    5010 | DR | 150.00
    2010 | CR | 150.00

    @ENTRY | Q1-3 | 2025-02-10 | February subscription revenue
    1200 | DR | 700.00
    4010 | CR | 700.00

    @ENTRY | Q1-4 | 2025-02-20 | February supplies expense
    5020 | DR | 90.00
    2010 | CR | 90.00
    """
    for entry in parse_journal_batch(raw):
        book.post_entry(entry)

    jan_is = book.income_statement(as_of="2025-01-31")
    assert jan_is == {
        "revenue_cents": 50000,
        "expense_cents": 15000,
        "net_income_cents": 35000,
    }

    jan_tb = book.trial_balance(as_of="2025-01-31")
    assert "5020" not in jan_tb
    assert jan_tb["TOTAL"] == {"debit_cents": 65000, "credit_cents": 65000}

    feb_is = book.income_statement(as_of="2025-02-28")
    assert feb_is == {
        "revenue_cents": 120000,
        "expense_cents": 24000,
        "net_income_cents": 96000,
    }
