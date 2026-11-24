from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any


CENT = Decimal("0.01")


def quantize_amount(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


class AccountType(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    EXPENSE = "EXPENSE"

    @property
    def normal_side(self) -> str:
        if self in (AccountType.ASSET, AccountType.EXPENSE):
            return "DEBIT"
        return "CREDIT"


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    account_type: AccountType


@dataclass(frozen=True)
class PostingLine:
    account_code: str
    side: str
    amount: Decimal


@dataclass(frozen=True)
class JournalEntry:
    entry_id: str
    date: str
    description: str
    lines: tuple[PostingLine, ...]


def parse_journal_entry(payload: dict[str, Any]) -> JournalEntry:
    entry_id = str(payload.get("entry_id", "")).strip()
    date = str(payload.get("date", "")).strip()
    description = str(payload.get("description", "")).strip()
    raw_lines = payload.get("lines") or []

    if not entry_id or not date:
        raise ValueError("entry_id and date are required")

    if len(raw_lines) != 2:
        raise ValueError("A journal entry must contain exactly 2 lines")

    parsed_lines: list[PostingLine] = []
    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")

    for item in raw_lines:
        account_code = str(item.get("account_code", "")).strip()
        side = str(item.get("side", "")).strip()
        amount = quantize_amount(item.get("amount", "0"))

        if not account_code:
            raise ValueError("account_code is required on every posting line")
        if side not in ("DEBIT", "CREDIT"):
            raise ValueError(f"Invalid posting side: {side}")
        if amount < Decimal("0.00"):
            raise ValueError("Posting amount must be positive")

        if side == "DEBIT":
            total_debits += amount
        else:
            total_credits += amount

        parsed_lines.append(
            PostingLine(account_code=account_code, side=side, amount=amount)
        )

    if total_debits != total_credits:
        raise ValueError(
            f"Unbalanced journal entry {entry_id}: debits={total_debits} credits={total_credits}"
        )

    return JournalEntry(
        entry_id=entry_id,
        date=date,
        description=description,
        lines=tuple(parsed_lines),
    )
