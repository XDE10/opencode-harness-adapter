from r07s2pkg.models import Account, AccountType, JournalEntry


class LedgerEngine:
    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._entries: dict[str, JournalEntry] = {}
        self._entry_order: list[str] = []

    def add_account(self, code: str, name: str, account_type: AccountType) -> Account:
        if code in self._accounts:
            raise ValueError(f"Account {code} already exists")
        account = Account(code=code, name=name, account_type=account_type)
        self._accounts[code] = account
        return account

    def get_account(self, code: str) -> Account:
        if code not in self._accounts:
            raise KeyError(f"Unknown account {code}")
        return self._accounts[code]

    def post_entry(self, entry: JournalEntry) -> JournalEntry:
        if entry.entry_id in self._entries:
            raise ValueError(f"Duplicate entry_id {entry.entry_id}")
        entry.validate()
        for line in entry.lines:
            if line.account_code not in self._accounts:
                raise KeyError(f"Unknown account {line.account_code}")
        for line in entry.lines:
            self._accounts[line.account_code].apply(line.debit, line.credit)
        self._entries[entry.entry_id] = entry
        self._entry_order.append(entry.entry_id)
        return entry

    def void_entry(self, entry_id: str, reversal_id: str, period: str) -> JournalEntry:
        if entry_id not in self._entries:
            raise KeyError(f"Unknown entry {entry_id}")
        original = self._entries[entry_id]
        if original.voided or original.reverses_id is not None:
            raise ValueError(f"Entry {entry_id} cannot be voided")
        reversal = original.build_reversal(reversal_id=reversal_id, period=period)
        self.post_entry(reversal)
        original.voided = True
        return reversal

    def trial_balance(self, up_to_period: str | None = None) -> dict[str, int]:
        totals: dict[str, int] = {code: 0 for code in self._accounts}
        for eid in self._entry_order:
            entry = self._entries[eid]
            if up_to_period is not None and entry.period > up_to_period:
                continue
            for line in entry.lines:
                totals[line.account_code] += line.debit - line.credit
        return {code: bal for code, bal in totals.items() if bal != 0}

    def income_statement(self, period: str | None = None) -> dict[str, int]:
        revenue = 0
        expense = 0
        for eid in self._entry_order:
            entry = self._entries[eid]
            if period is not None and entry.period != period:
                continue
            for line in entry.lines:
                account = self._accounts[line.account_code]
                delta = account.signed_delta(line.debit, line.credit)
                if account.account_type == AccountType.REVENUE:
                    revenue += delta
                elif account.account_type == AccountType.EXPENSE:
                    expense += delta
        return {
            "revenue": revenue,
            "expense": expense,
            "net_income": revenue - expense,
        }
