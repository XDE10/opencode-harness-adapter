Fix `run_bookings(num_rooms, ops)` in `solution.py`.

Implement a deterministic room-booking and blackout engine over half-open integer time intervals `[start, end)`.
- `num_rooms`: positive integer (`>= 1`) representing rooms numbered `0` through `num_rooms - 1`. Raise `ValueError` if `num_rooms < 1`.
- Every interval `[start, end)` is half-open: two intervals `[a, b)` and `[c, d)` overlap if and only if `max(a, c) < min(b, d)`. Touching endpoints (`b == c`) do **not** overlap.
- Raise `ValueError` on any operation specifying `start >= end`, an unknown `"op"`, or (for `"blackout"` / `"free_slots"`) a `room` outside `0 <= room < num_rooms`.
- `ops`: list of operation dicts executed sequentially, returning a list of results (one per operation):
  1. `{"op": "book", "id": str, "start": int, "end": int, "room": int | None}`:
     - If `id` is already an active booking ID, raise `ValueError`.
     - If `"room"` is provided and not `None`, verify `0 <= room < num_rooms` (else raise `ValueError`). The booking may only be placed in that specific room if `[start, end)` does not overlap any active booking or blackout window in that room.
     - If `"room"` is omitted or `None`, assign the **lowest-numbered** room `r` in `0 .. num_rooms - 1` where `[start, end)` does not overlap any active booking or blackout window in `r`.
     - If a valid room is found, record the active booking and append the assigned room index (`int`) to results; otherwise do not record the booking and append `-1`.
  2. `{"op": "cancel", "id": str}`:
     - If `id` is an active booking, remove it and append `True`; otherwise append `False`. (A cancelled `id` can be reused by a future `"book"` operation.)
  3. `{"op": "blackout", "room": int, "start": int, "end": int}`:
     - Add a persistent blackout window `[start, end)` to `room`.
     - Any active bookings in `room` that overlap `[start, end)` are immediately evicted (and their IDs cease to be active).
     - Append the sorted list of evicted booking IDs (`list[str]`).
  4. `{"op": "free_slots", "room": int, "start": int, "end": int}`:
     - Return the sorted list of maximal contiguous free sub-intervals `[[s, e], ...]` within `[start, end)` in `room` that are not covered by any active booking or blackout window in `room`.

Example:
```python
run_bookings(2, [
    {"op": "book", "id": "b1", "start": 10, "end": 20, "room": None},
    {"op": "book", "id": "b2", "start": 20, "end": 30, "room": 0},
    {"op": "blackout", "room": 0, "start": 15, "end": 25},
    {"op": "free_slots", "room": 0, "start": 0, "end": 30},
])
# Returns: [0, 0, ["b1", "b2"], [[0, 15], [25, 30]]]
```
