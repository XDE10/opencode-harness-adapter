from r07s3pkg import (
    Account,
    AccountType,
    LedgerBook,
    parse_amount_cents,
    parse_journal_batch,
)


def test_parse_amount_cents_exact():
    assert parse_amount_cents("19.99") == 1999
    assert parse_amount_cents("250") == 25000


def test_simple_posting_and_trial_balance():
    book = LedgerBook()
    book.register_account(Account("1000", "Cash", AccountType.ASSET))
    book.register_account(Account("3000", "Common Stock", AccountType.EQUITY))
    book.register_account(Account("4000", "Service Revenue", AccountType.REVENUE))
    book.register_account(Account("5000", "Rent Expense", AccountType.EXPENSE))

    batch = """
    @ENTRY | J-1 | 2025-01-01 | Initial capital
    1000 | DR | 1000.00 | Founder investment
    3000 | CR | 1000.00 | Shares issued

    @ENTRY | J-2 | 2025-01-05 | Customer invoice paid
    1000 | DR | 450.00
    4000 | CR | 450.00
    """
    for entry in parse_journal_batch(batch):
        book.post_entry(entry)

    assert book.account_balance("1000") == 145000
    tb = book.trial_balance()
    assert tb["TOTAL"]["debit_cents"] == 145000
    assert tb["TOTAL"]["credit_cents"] == 145000
