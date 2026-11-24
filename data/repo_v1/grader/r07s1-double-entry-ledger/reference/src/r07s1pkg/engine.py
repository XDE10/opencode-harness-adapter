from decimal import Decimal
from typing import Any

from r07s1pkg.models import (
    CENT,
    Account,
    AccountType,
    JournalEntry,
    parse_journal_entry,
)


class LedgerBook:
    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._entries: list[JournalEntry] = []
        self._entry_ids: set[str] = set()

    def add_account(self, code: str, name: str, account_type: AccountType) -> Account:
        if code in self._accounts:
            raise ValueError(f"Account already exists: {code}")
        account = Account(code=code, name=name, account_type=account_type)
        self._accounts[code] = account
        return account

    def post_entry(self, entry_or_payload: JournalEntry | dict[str, Any]) -> JournalEntry:
        entry = (
            entry_or_payload
            if isinstance(entry_or_payload, JournalEntry)
            else parse_journal_entry(entry_or_payload)
        )

        if entry.entry_id in self._entry_ids:
            raise ValueError(f"Duplicate entry_id: {entry.entry_id}")

        for line in entry.lines:
            if line.account_code not in self._accounts:
                raise ValueError(f"Unknown account_code: {line.account_code}")

        self._entries.append(entry)
        self._entry_ids.add(entry.entry_id)
        return entry

    def _iter_entries(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[JournalEntry]:
        result: list[JournalEntry] = []
        for entry in self._entries:
            if start_date is not None and entry.date < start_date:
                continue
            if end_date is not None and entry.date > end_date:
                continue
            result.append(entry)
        return result

    def get_balance(self, account_code: str, up_to_date: str | None = None) -> Decimal:
        if account_code not in self._accounts:
            raise ValueError(f"Unknown account_code: {account_code}")

        account = self._accounts[account_code]
        debits = Decimal("0.00")
        credits = Decimal("0.00")

        for entry in self._iter_entries(end_date=up_to_date):
            for line in entry.lines:
                if line.account_code == account_code:
                    if line.side == "DEBIT":
                        debits += line.amount
                    else:
                        credits += line.amount

        if account.account_type.normal_side == "DEBIT":
            return (debits - credits).quantize(CENT)
        return (credits - debits).quantize(CENT)

    def trial_balance(self, up_to_date: str | None = None) -> dict[str, Any]:
        accounts_report: dict[str, dict[str, Decimal]] = {}
        total_debits = Decimal("0.00")
        total_credits = Decimal("0.00")

        for code in sorted(self._accounts):
            account = self._accounts[code]
            bal = self.get_balance(code, up_to_date=up_to_date)
            if account.account_type.normal_side == "DEBIT":
                if bal >= Decimal("0.00"):
                    debit_col = bal
                    credit_col = Decimal("0.00")
                else:
                    debit_col = Decimal("0.00")
                    credit_col = abs(bal)
            else:
                if bal >= Decimal("0.00"):
                    debit_col = Decimal("0.00")
                    credit_col = bal
                else:
                    debit_col = abs(bal)
                    credit_col = Decimal("0.00")

            accounts_report[code] = {"debit": debit_col, "credit": credit_col}
            total_debits += debit_col
            total_credits += credit_col

        return {
            "total_debits": total_debits.quantize(CENT),
            "total_credits": total_credits.quantize(CENT),
            "accounts": accounts_report,
        }

    def income_statement(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Decimal]:
        revenue = Decimal("0.00")
        expenses = Decimal("0.00")

        for entry in self._iter_entries(start_date=start_date, end_date=end_date):
            for line in entry.lines:
                acct = self._accounts[line.account_code]
                if acct.account_type == AccountType.REVENUE:
                    if line.side == "CREDIT":
                        revenue += line.amount
                    else:
                        revenue -= line.amount
                elif acct.account_type == AccountType.EXPENSE:
                    if line.side == "DEBIT":
                        expenses += line.amount
                    else:
                        expenses -= line.amount

        return {
            "revenue": revenue.quantize(CENT),
            "expenses": expenses.quantize(CENT),
            "net_income": (revenue - expenses).quantize(CENT),
        }
