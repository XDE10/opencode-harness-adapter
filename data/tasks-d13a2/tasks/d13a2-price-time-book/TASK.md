Fix `run(ops)` in `solution.py`.

Implement a deterministic price-time priority limit order book. `ops` must be a list, and each operation must be a dict; otherwise raise `ValueError`. Extra keys in operation dicts are ignored.

State rules:
- Each accepted `add` creates one resting order with a sequence number starting at `0`, increasing by `1` for each accepted add.
- Order ids are strings and must be unique among currently live orders. A canceled or fully filled id may be reused.
- All required integer fields must be positive `int` values; `bool` is not accepted as an integer. Invalid types, invalid sides, missing fields, duplicate live ids, and unknown operations raise `ValueError`.

Operations:
1. `{"op": "add", "id": str, "side": "buy"|"sell", "price": int, "qty": int}`
   Append `None`.
2. `{"op": "cancel", "id": str}`
   Remove the live order with that id if present. Append `True` if removed, otherwise `False`.
3. `{"op": "match", "side": "buy"|"sell", "limit": int, "qty": int}`
   Match an aggressive order against resting opposite orders. For `side == "buy"`, eligible asks have `price <= limit` and are executed in ascending price order, then ascending sequence order. For `side == "sell"`, eligible bids have `price >= limit` and are executed in descending price order, then ascending sequence order. Each fill uses the resting order's price. Fully filled orders are removed; partially filled orders keep their original sequence number. The aggressive order is never inserted; any remaining aggressive quantity is discarded. Append the fills in execution order as dicts `{"id": str, "qty": int, "price": int}`.
4. `{"op": "book"}`
   Append a snapshot `{"bids": [...], "asks": [...]}`. Bids are sorted by descending price then ascending sequence; asks by ascending price then ascending sequence. Each entry is `[price, remaining_qty, seq]`.

Example:
`run([{"op": "add", "id": "a", "side": "sell", "price": 10, "qty": 5}, {"op": "match", "side": "buy", "limit": 10, "qty": 3}, {"op": "book"}])` returns `[None, [{"id": "a", "qty": 3, "price": 10}], {"bids": [], "asks": [[10, 2, 0]]}]`.

If two resting orders have the same price, the earlier sequence is always filled first, regardless of side.
