import pytest

from r07s2pkg import AccountType, JournalEntry, JournalLine, LedgerEngine


def _build_standard_ledger() -> LedgerEngine:
    engine = LedgerEngine()
    engine.add_account("1000", "Cash", AccountType.ASSET)
    engine.add_account("1100", "Accounts Receivable", AccountType.ASSET)
    engine.add_account("2000", "Accounts Payable", AccountType.LIABILITY)
    engine.add_account("3000", "Owner Equity", AccountType.EQUITY)
    engine.add_account("4000", "Sales Revenue", AccountType.REVENUE)
    engine.add_account("5000", "Hosting Expense", AccountType.EXPENSE)
    return engine


def test_unbalanced_or_invalid_entry_rejected():
    engine = _build_standard_ledger()
    bad_entry = JournalEntry(
        entry_id="JE-BAD",
        period="2025-01",
        description="Unbalanced",
        lines=[
            JournalLine("1000", debit=1000),
            JournalLine("4000", credit=900),
        ],
    )
    with pytest.raises(ValueError):
        engine.post_entry(bad_entry)
    assert engine.get_account("1000").balance == 0


def test_duplicate_entry_and_unknown_account_rejected():
    engine = _build_standard_ledger()
    valid = JournalEntry(
        entry_id="JE-1",
        period="2025-01",
        description="Valid",
        lines=[
            JournalLine("1000", debit=500),
            JournalLine("4000", credit=500),
        ],
    )
    engine.post_entry(valid)
    with pytest.raises(ValueError):
        engine.post_entry(valid)

    unknown_acct = JournalEntry(
        entry_id="JE-2",
        period="2025-01",
        description="Missing account",
        lines=[
            JournalLine("9999", debit=500),
            JournalLine("4000", credit=500),
        ],
    )
    with pytest.raises(KeyError):
        engine.post_entry(unknown_acct)


def test_void_conflict_double_void_and_reversal_void_blocked():
    engine = _build_standard_ledger()
    engine.post_entry(
        JournalEntry(
            entry_id="JE-10",
            period="2025-01",
            description="Initial sale",
            lines=[
                JournalLine("1000", debit=2000),
                JournalLine("4000", credit=2000),
            ],
        )
    )
    rev = engine.void_entry("JE-10", reversal_id="JE-10-REV", period="2025-01")
    assert rev.reverses_id == "JE-10"

    with pytest.raises(ValueError):
        engine.void_entry("JE-10", reversal_id="JE-10-REV2", period="2025-01")

    with pytest.raises(ValueError):
        engine.void_entry("JE-10-REV", reversal_id="JE-10-REV3", period="2025-01")


def test_build_reversal_swaps_debits_and_credits():
    entry = JournalEntry(
        entry_id="JE-100",
        period="2025-01",
        description="Compound entry",
        lines=[
            JournalLine("1000", debit=3000),
            JournalLine("1100", debit=2000),
            JournalLine("4000", credit=5000),
        ],
    )
    rev = entry.build_reversal(reversal_id="JE-100-R", period="2025-02")
    assert rev.entry_id == "JE-100-R"
    assert rev.period == "2025-02"
    assert rev.reverses_id == "JE-100"
    assert [(l.account_code, l.debit, l.credit) for l in rev.lines] == [
        ("1000", 0, 3000),
        ("1100", 0, 2000),
        ("4000", 5000, 0),
    ]


def test_void_entry_restores_account_balances_and_income_statement():
    engine = _build_standard_ledger()
    engine.post_entry(
        JournalEntry(
            entry_id="JE-1",
            period="2025-01",
            description="Sale A",
            lines=[
                JournalLine("1000", debit=8000),
                JournalLine("4000", credit=8000),
            ],
        )
    )
    engine.post_entry(
        JournalEntry(
            entry_id="JE-2",
            period="2025-01",
            description="Erroneous sale B",
            lines=[
                JournalLine("1000", debit=3000),
                JournalLine("4000", credit=3000),
            ],
        )
    )
    engine.void_entry("JE-2", reversal_id="JE-2-VOID", period="2025-01")

    assert engine.get_account("1000").balance == 8000
    assert engine.get_account("4000").balance == 8000
    assert engine.income_statement(period="2025-01") == {
        "revenue": 8000,
        "expense": 0,
        "net_income": 8000,
    }


def test_cross_period_void_adjustment_in_subsequent_period():
    engine = _build_standard_ledger()
    engine.post_entry(
        JournalEntry(
            entry_id="JE-JAN",
            period="2025-01",
            description="Accrued hosting expense",
            lines=[
                JournalLine("5000", debit=4500),
                JournalLine("2000", credit=4500),
            ],
        )
    )
    engine.void_entry("JE-JAN", reversal_id="JE-FEB-REV", period="2025-02")

    assert engine.get_account("5000").balance == 0
    assert engine.get_account("2000").balance == 0
    assert engine.income_statement(period="2025-01") == {
        "revenue": 0,
        "expense": 4500,
        "net_income": -4500,
    }
    assert engine.income_statement(period="2025-02") == {
        "revenue": 0,
        "expense": -4500,
        "net_income": 4500,
    }
    assert engine.income_statement() == {
        "revenue": 0,
        "expense": 0,
        "net_income": 0,
    }


def test_trial_balance_uses_normal_balance_sign_for_credit_accounts():
    engine = _build_standard_ledger()
    engine.post_entry(
        JournalEntry(
            entry_id="JE-CAP",
            period="2025-01",
            description="Capital contribution",
            lines=[
                JournalLine("1000", debit=25000),
                JournalLine("3000", credit=25000),
            ],
        )
    )
    engine.post_entry(
        JournalEntry(
            entry_id="JE-EXP",
            period="2025-01",
            description="Vendor bill on credit",
            lines=[
                JournalLine("5000", debit=4000),
                JournalLine("2000", credit=4000),
            ],
        )
    )

    tb = engine.trial_balance()
    assert tb == {
        "1000": 25000,
        "3000": 25000,
        "5000": 4000,
        "2000": 4000,
    }


def test_trial_balance_up_to_period_filtering_and_zero_omission():
    engine = _build_standard_ledger()
    engine.post_entry(
        JournalEntry(
            entry_id="JE-1",
            period="2025-01",
            description="Jan revenue",
            lines=[
                JournalLine("1100", debit=6000),
                JournalLine("4000", credit=6000),
            ],
        )
    )
    engine.post_entry(
        JournalEntry(
            entry_id="JE-2",
            period="2025-02",
            description="Collect AR in Feb",
            lines=[
                JournalLine("1000", debit=6000),
                JournalLine("1100", credit=6000),
            ],
        )
    )

    tb_jan = engine.trial_balance(up_to_period="2025-01")
    assert tb_jan == {"1100": 6000, "4000": 6000}

    tb_feb = engine.trial_balance(up_to_period="2025-02")
    assert tb_feb == {"1000": 6000, "4000": 6000}
    assert "1100" not in tb_feb


def test_multi_step_void_and_period_trial_balance_composition():
    engine = _build_standard_ledger()
    engine.post_entry(
        JournalEntry(
            entry_id="JE-1",
            period="2025-01",
            description="Jan invoice",
            lines=[
                JournalLine("1100", debit=9000),
                JournalLine("4000", credit=9000),
            ],
        )
    )
    engine.post_entry(
        JournalEntry(
            entry_id="JE-2",
            period="2025-02",
            description="Disputed Feb invoice",
            lines=[
                JournalLine("1100", debit=5000),
                JournalLine("4000", credit=5000),
            ],
        )
    )
    engine.void_entry("JE-2", reversal_id="JE-2-REV", period="2025-03")

    assert engine.trial_balance(up_to_period="2025-01") == {"1100": 9000, "4000": 9000}
    assert engine.trial_balance(up_to_period="2025-02") == {"1100": 14000, "4000": 14000}
    assert engine.trial_balance(up_to_period="2025-03") == {"1100": 9000, "4000": 9000}
