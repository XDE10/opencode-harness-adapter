from dataclasses import dataclass, field
from enum import Enum


class AccountType(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


DEBIT_NORMAL_TYPES = {AccountType.ASSET, AccountType.EXPENSE}


@dataclass
class Account:
    code: str
    name: str
    account_type: AccountType
    balance: int = 0

    @property
    def is_debit_normal(self) -> bool:
        return self.account_type in DEBIT_NORMAL_TYPES

    def signed_delta(self, debit: int, credit: int) -> int:
        if self.is_debit_normal:
            return debit - credit
        return credit - debit

    def apply(self, debit: int, credit: int) -> None:
        self.balance += self.signed_delta(debit, credit)


@dataclass(frozen=True)
class JournalLine:
    account_code: str
    debit: int = 0
    credit: int = 0

    def __post_init__(self) -> None:
        if self.debit < 0 or self.credit < 0:
            raise ValueError("Line amounts must be non-negative")
        if (self.debit == 0 and self.credit == 0) or (self.debit > 0 and self.credit > 0):
            raise ValueError("Each line must have either a positive debit or a positive credit")


@dataclass
class JournalEntry:
    entry_id: str
    period: str
    description: str
    lines: list[JournalLine] = field(default_factory=list)
    voided: bool = False
    reverses_id: str | None = None

    def validate(self) -> None:
        if len(self.lines) < 2:
            raise ValueError("Journal entry requires at least two lines")
        total_debit = sum(line.debit for line in self.lines)
        total_credit = sum(line.credit for line in self.lines)
        if total_debit <= 0 or total_debit != total_credit:
            raise ValueError(f"Unbalanced journal entry {self.entry_id}: {total_debit} != {total_credit}")

    def build_reversal(self, reversal_id: str, period: str) -> "JournalEntry":
        reversed_lines = [
            JournalLine(
                account_code=line.account_code,
                debit=line.credit,
                credit=line.debit,
            )
            for line in self.lines
        ]
        return JournalEntry(
            entry_id=reversal_id,
            period=period,
            description=f"REVERSAL of {self.entry_id}",
            lines=reversed_lines,
            reverses_id=self.entry_id,
        )
