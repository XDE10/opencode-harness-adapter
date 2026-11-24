from decimal import Decimal, InvalidOperation
from r07s3pkg.models import JournalEntry, PostingLeg


def parse_amount_cents(token: str) -> int:
    cleaned = token.strip()
    if not cleaned:
        raise ValueError("Empty amount token")
    try:
        dec = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid monetary amount: {token!r}") from exc
    if dec <= 0:
        raise ValueError("Amount must be positive")
    exponent = dec.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -2:
        raise ValueError(f"Amount has more than 2 decimal places: {token!r}")
    return int((dec * Decimal("100")).to_integral_exact())


def parse_journal_batch(raw_text: str) -> list[JournalEntry]:
    entries: list[JournalEntry] = []
    current_header: tuple[str, str, str] | None = None
    current_legs_by_account: dict[str, PostingLeg] = {}

    def flush_current() -> None:
        nonlocal current_header, current_legs_by_account
        if current_header is not None:
            entry_id, posted_date, desc = current_header
            entries.append(
                JournalEntry(
                    entry_id=entry_id,
                    posted_date=posted_date,
                    description=desc,
                    legs=tuple(current_legs_by_account.values()),
                )
            )
            current_header = None
            current_legs_by_account = {}

    for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = [p.strip() for p in stripped.split("|")]
        if parts[0] == "@ENTRY":
            flush_current()
            if len(parts) != 4 or not parts[1] or not parts[2]:
                raise ValueError(f"Invalid @ENTRY header at line {line_no}")
            current_header = (parts[1], parts[2], parts[3])
        else:
            if current_header is None:
                raise ValueError(f"Orphan leg before @ENTRY at line {line_no}")
            if len(parts) not in (3, 4):
                raise ValueError(f"Invalid leg format at line {line_no}")
            acc_code = parts[0]
            side = parts[1]
            amount_cents = parse_amount_cents(parts[2])
            memo = parts[3] if len(parts) == 4 else ""
            current_legs_by_account[acc_code] = PostingLeg(
                account_code=acc_code,
                side=side,
                amount_cents=amount_cents,
                memo=memo,
            )

    flush_current()
    return entries
