from r07s3pkg.models import Account, AccountType, JournalEntry


class LedgerBook:
    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._entries: list[JournalEntry] = []
        self._posted_ids: set[str] = set()

    def register_account(self, account: Account) -> None:
        if account.code in self._accounts:
            raise ValueError(f"Duplicate account code: {account.code}")
        self._accounts[account.code] = account

    @property
    def entries(self) -> tuple[JournalEntry, ...]:
        return tuple(self._entries)

    def post_entry(self, entry: JournalEntry) -> None:
        if entry.entry_id in self._posted_ids:
            raise ValueError(f"Duplicate entry_id: {entry.entry_id}")
        for leg in entry.legs:
            if leg.account_code not in self._accounts:
                raise KeyError(f"Unknown account code: {leg.account_code}")
        self._entries.append(entry)
        self._posted_ids.add(entry.entry_id)

    def account_balance(self, account_code: str, as_of: str | None = None) -> int:
        if account_code not in self._accounts:
            raise KeyError(f"Unknown account code: {account_code}")
        account = self._accounts[account_code]
        total = 0
        for entry in self._entries:
            if as_of is not None and entry.posted_date > as_of:
                continue
            for leg in entry.legs:
                if leg.account_code == account_code:
                    total += account.signed_delta(leg.side, leg.amount_cents)
        return total

    def trial_balance(self, as_of: str | None = None) -> dict[str, dict[str, int]]:
        report: dict[str, dict[str, int]] = {}
        total_dr = 0
        total_cr = 0
        for code in sorted(self._accounts):
            account = self._accounts[code]
            bal = self.account_balance(code, as_of=as_of)
            if bal == 0:
                continue
            net_dr = bal if account.normal_side == "DR" else -bal
            if net_dr > 0:
                report[code] = {"debit_cents": net_dr, "credit_cents": 0}
                total_dr += net_dr
            else:
                report[code] = {"debit_cents": 0, "credit_cents": -net_dr}
                total_cr += -net_dr
        report["TOTAL"] = {"debit_cents": total_dr, "credit_cents": total_cr}
        return report

    def income_statement(self, as_of: str | None = None) -> dict[str, int]:
        revenue = 0
        expense = 0
        for code, account in self._accounts.items():
            if account.account_type == AccountType.REVENUE:
                revenue += self.account_balance(code, as_of=as_of)
            elif account.account_type == AccountType.EXPENSE:
                expense += self.account_balance(code, as_of=as_of)
        return {
            "revenue_cents": revenue,
            "expense_cents": expense,
            "net_income_cents": revenue - expense,
        }
