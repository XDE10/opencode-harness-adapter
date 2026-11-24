from decimal import Decimal
import pytest

from r07s1pkg import AccountType, LedgerBook, parse_journal_entry


def _build_standard_ledger() -> LedgerBook:
    ledger = LedgerBook()
    ledger.add_account("1000", "Cash", AccountType.ASSET)
    ledger.add_account("1200", "Accounts Receivable", AccountType.ASSET)
    ledger.add_account("2000", "Accounts Payable", AccountType.LIABILITY)
    ledger.add_account("2100", "Sales Tax Payable", AccountType.LIABILITY)
    ledger.add_account("3000", "Owner Equity", AccountType.EQUITY)
    ledger.add_account("4000", "Service Revenue", AccountType.REVENUE)
    ledger.add_account("5000", "Rent Expense", AccountType.EXPENSE)
    ledger.add_account("5100", "Utilities Expense", AccountType.EXPENSE)
    return ledger


def test_duplicate_account_and_unknown_account_validation():
    ledger = _build_standard_ledger()
    with pytest.raises(ValueError):
        ledger.add_account("1000", "Duplicate Cash", AccountType.ASSET)

    with pytest.raises(ValueError):
        ledger.post_entry(
            {
                "entry_id": "JE-99",
                "date": "2025-01-01",
                "description": "Missing account",
                "lines": [
                    {"account_code": "1000", "side": "DEBIT", "amount": "50.00"},
                    {"account_code": "9999", "side": "CREDIT", "amount": "50.00"},
                ],
            }
        )


def test_duplicate_entry_id_rejected():
    ledger = _build_standard_ledger()
    payload = {
        "entry_id": "JE-100",
        "date": "2025-01-05",
        "description": "Capital contribution",
        "lines": [
            {"account_code": "1000", "side": "DEBIT", "amount": "250.00"},
            {"account_code": "3000", "side": "CREDIT", "amount": "250.00"},
        ],
    }
    ledger.post_entry(payload)
    with pytest.raises(ValueError):
        ledger.post_entry(payload)
    assert ledger.get_balance("1000") == Decimal("250.00")


def test_asset_and_liability_up_to_date_filtering():
    ledger = _build_standard_ledger()
    ledger.post_entry(
        {
            "entry_id": "JE-1",
            "date": "2025-01-10",
            "description": "Borrow cash",
            "lines": [
                {"account_code": "1000", "side": "DEBIT", "amount": "1000.00"},
                {"account_code": "2000", "side": "CREDIT", "amount": "1000.00"},
            ],
        }
    )
    ledger.post_entry(
        {
            "entry_id": "JE-2",
            "date": "2025-01-20",
            "description": "Partial repayment",
            "lines": [
                {"account_code": "2000", "side": "DEBIT", "amount": "400.00"},
                {"account_code": "1000", "side": "CREDIT", "amount": "400.00"},
            ],
        }
    )
    assert ledger.get_balance("1000", up_to_date="2025-01-15") == Decimal("1000.00")
    assert ledger.get_balance("2000", up_to_date="2025-01-15") == Decimal("1000.00")
    assert ledger.get_balance("1000", up_to_date="2025-01-20") == Decimal("600.00")
    assert ledger.get_balance("2000", up_to_date="2025-01-20") == Decimal("600.00")


def test_parse_multi_line_split_entry_and_case_normalization():
    entry = parse_journal_entry(
        {
            "entry_id": "JE-SPLIT-1",
            "date": "2025-02-01",
            "description": "Invoice with sales tax",
            "lines": [
                {"account_code": "1000", "side": "debit", "amount": "108.25"},
                {"account_code": "4000", "side": "credit", "amount": "100.00"},
                {"account_code": "2100", "side": "Credit", "amount": "8.25"},
            ],
        }
    )
    assert len(entry.lines) == 3
    assert entry.lines[0].side == "DEBIT"
    assert entry.lines[2].side == "CREDIT"
    assert entry.lines[0].amount == Decimal("108.25")


def test_parse_rejects_zero_amount_and_single_line():
    with pytest.raises(ValueError):
        parse_journal_entry(
            {
                "entry_id": "JE-ZERO",
                "date": "2025-02-01",
                "description": "Zero line amount",
                "lines": [
                    {"account_code": "1000", "side": "DEBIT", "amount": "0.00"},
                    {"account_code": "3000", "side": "CREDIT", "amount": "0.00"},
                ],
            }
        )

    with pytest.raises(ValueError):
        parse_journal_entry(
            {
                "entry_id": "JE-ONE",
                "date": "2025-02-01",
                "description": "Single line",
                "lines": [
                    {"account_code": "1000", "side": "DEBIT", "amount": "10.00"},
                ],
            }
        )


def test_revenue_and_expense_normal_balances():
    ledger = _build_standard_ledger()
    ledger.post_entry(
        {
            "entry_id": "JE-REV-1",
            "date": "2025-02-05",
            "description": "Cash sale",
            "lines": [
                {"account_code": "1000", "side": "DEBIT", "amount": "750.00"},
                {"account_code": "4000", "side": "CREDIT", "amount": "750.00"},
            ],
        }
    )
    ledger.post_entry(
        {
            "entry_id": "JE-EXP-1",
            "date": "2025-02-06",
            "description": "Pay rent",
            "lines": [
                {"account_code": "5000", "side": "DEBIT", "amount": "300.00"},
                {"account_code": "1000", "side": "CREDIT", "amount": "300.00"},
            ],
        }
    )

    assert ledger.get_balance("4000") == Decimal("750.00")
    assert ledger.get_balance("5000") == Decimal("300.00")
    assert ledger.get_balance("1000") == Decimal("450.00")


def test_trial_balance_matches_with_contra_overdrawn_account():
    ledger = _build_standard_ledger()
    ledger.post_entry(
        {
            "entry_id": "JE-TB-1",
            "date": "2025-02-10",
            "description": "Sale on cash",
            "lines": [
                {"account_code": "1000", "side": "DEBIT", "amount": "200.00"},
                {"account_code": "4000", "side": "CREDIT", "amount": "200.00"},
            ],
        }
    )
    ledger.post_entry(
        {
            "entry_id": "JE-TB-2",
            "date": "2025-02-11",
            "description": "Overdraft cash for rent",
            "lines": [
                {"account_code": "5000", "side": "DEBIT", "amount": "350.00"},
                {"account_code": "1000", "side": "CREDIT", "amount": "350.00"},
            ],
        }
    )

    tb = ledger.trial_balance()
    assert tb["total_debits"] == Decimal("350.00")
    assert tb["total_credits"] == Decimal("350.00")
    assert tb["accounts"]["1000"] == {
        "debit": Decimal("0.00"),
        "credit": Decimal("150.00"),
    }
    assert tb["accounts"]["4000"] == {
        "debit": Decimal("0.00"),
        "credit": Decimal("200.00"),
    }
    assert tb["accounts"]["5000"] == {
        "debit": Decimal("350.00"),
        "credit": Decimal("0.00"),
    }


def test_income_statement_inclusive_start_and_end_dates():
    ledger = _build_standard_ledger()
    ledger.post_entry(
        {
            "entry_id": "JE-JAN",
            "date": "2025-01-31",
            "description": "Jan revenue",
            "lines": [
                {"account_code": "1000", "side": "DEBIT", "amount": "500.00"},
                {"account_code": "4000", "side": "CREDIT", "amount": "500.00"},
            ],
        }
    )
    ledger.post_entry(
        {
            "entry_id": "JE-FEB-START",
            "date": "2025-02-01",
            "description": "Feb 1 revenue",
            "lines": [
                {"account_code": "1000", "side": "DEBIT", "amount": "800.00"},
                {"account_code": "4000", "side": "CREDIT", "amount": "800.00"},
            ],
        }
    )
    ledger.post_entry(
        {
            "entry_id": "JE-FEB-END",
            "date": "2025-02-28",
            "description": "Feb 28 rent and utilities",
            "lines": [
                {"account_code": "5000", "side": "DEBIT", "amount": "250.00"},
                {"account_code": "5100", "side": "DEBIT", "amount": "50.00"},
                {"account_code": "1000", "side": "CREDIT", "amount": "300.00"},
            ],
        }
    )

    stmt = ledger.income_statement(start_date="2025-02-01", end_date="2025-02-28")
    assert stmt == {
        "revenue": Decimal("800.00"),
        "expenses": Decimal("300.00"),
        "net_income": Decimal("500.00"),
    }
