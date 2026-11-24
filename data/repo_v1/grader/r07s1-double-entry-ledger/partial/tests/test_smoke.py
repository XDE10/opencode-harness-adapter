from decimal import Decimal
import pytest

from r07s1pkg import AccountType, LedgerBook, parse_journal_entry


def test_basic_two_line_entry_and_asset_equity_balance():
    ledger = LedgerBook()
    ledger.add_account("1000", "Cash", AccountType.ASSET)
    ledger.add_account("3000", "Common Stock", AccountType.EQUITY)

    entry = parse_journal_entry(
        {
            "entry_id": "JE-1",
            "date": "2025-01-01",
            "description": "Initial investment",
            "lines": [
                {"account_code": "1000", "side": "DEBIT", "amount": "500.00"},
                {"account_code": "3000", "side": "CREDIT", "amount": "500.00"},
            ],
        }
    )
    ledger.post_entry(entry)

    assert ledger.get_balance("1000") == Decimal("500.00")
    assert ledger.get_balance("3000") == Decimal("500.00")


def test_unbalanced_entry_rejected():
    with pytest.raises(ValueError):
        parse_journal_entry(
            {
                "entry_id": "JE-2",
                "date": "2025-01-02",
                "description": "Broken entry",
                "lines": [
                    {"account_code": "1000", "side": "DEBIT", "amount": "100.00"},
                    {"account_code": "3000", "side": "CREDIT", "amount": "90.00"},
                ],
            }
        )
