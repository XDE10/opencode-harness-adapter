from r07s2pkg import AccountType, JournalEntry, JournalLine, LedgerEngine


def test_post_and_account_balances():
    engine = LedgerEngine()
    engine.add_account("1000", "Cash", AccountType.ASSET)
    engine.add_account("4000", "Sales Revenue", AccountType.REVENUE)

    entry = JournalEntry(
        entry_id="JE-1",
        period="2025-01",
        description="Cash sale",
        lines=[
            JournalLine("1000", debit=5000),
            JournalLine("4000", credit=5000),
        ],
    )
    engine.post_entry(entry)

    assert engine.get_account("1000").balance == 5000
    assert engine.get_account("4000").balance == 5000


def test_income_statement_basic():
    engine = LedgerEngine()
    engine.add_account("1000", "Cash", AccountType.ASSET)
    engine.add_account("4000", "Service Revenue", AccountType.REVENUE)
    engine.add_account("5000", "Rent Expense", AccountType.EXPENSE)

    engine.post_entry(
        JournalEntry(
            entry_id="JE-1",
            period="2025-01",
            description="Client invoice paid",
            lines=[
                JournalLine("1000", debit=12000),
                JournalLine("4000", credit=12000),
            ],
        )
    )
    engine.post_entry(
        JournalEntry(
            entry_id="JE-2",
            period="2025-01",
            description="Office rent",
            lines=[
                JournalLine("5000", debit=3500),
                JournalLine("1000", credit=3500),
            ],
        )
    )

    stmt = engine.income_statement(period="2025-01")
    assert stmt == {"revenue": 12000, "expense": 3500, "net_income": 8500}
