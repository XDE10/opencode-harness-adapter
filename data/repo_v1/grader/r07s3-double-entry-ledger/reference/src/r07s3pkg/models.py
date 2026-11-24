from dataclasses import dataclass
from enum import Enum


class AccountType(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"


DEBIT_NORMAL_TYPES = {AccountType.ASSET, AccountType.EXPENSE}


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    account_type: AccountType

    @property
    def normal_side(self) -> str:
        return "DR" if self.account_type in DEBIT_NORMAL_TYPES else "CR"

    def signed_delta(self, side: str, amount_cents: int) -> int:
        norm_side = side.strip().upper()
        if norm_side not in ("DR", "CR"):
            raise ValueError(f"Invalid posting side: {side!r}")
        if amount_cents <= 0:
            raise ValueError("Posting amount_cents must be positive")
        if norm_side == self.normal_side:
            return amount_cents
        return -amount_cents


@dataclass(frozen=True)
class PostingLeg:
    account_code: str
    side: str
    amount_cents: int
    memo: str = ""

    def __post_init__(self) -> None:
        norm_code = self.account_code.strip()
        norm_side = self.side.strip().upper()
        if not norm_code:
            raise ValueError("account_code cannot be empty")
        if norm_side not in ("DR", "CR"):
            raise ValueError(f"Invalid side: {self.side!r}")
        if self.amount_cents <= 0:
            raise ValueError("amount_cents must be > 0")
        object.__setattr__(self, "account_code", norm_code)
        object.__setattr__(self, "side", norm_side)


@dataclass(frozen=True)
class JournalEntry:
    entry_id: str
    posted_date: str
    description: str
    legs: tuple[PostingLeg, ...]

    def __post_init__(self) -> None:
        if len(self.legs) < 2:
            raise ValueError("JournalEntry requires at least 2 legs")
        dr_total = sum(leg.amount_cents for leg in self.legs if leg.side == "DR")
        cr_total = sum(leg.amount_cents for leg in self.legs if leg.side == "CR")
        if dr_total != cr_total:
            raise ValueError(
                f"Unbalanced JournalEntry {self.entry_id}: DR={dr_total} != CR={cr_total}"
            )
