Fix `allocate_rooms(requests, max_rooms, turnaround)` in `solution.py`.

You are implementing a deterministic meeting room allocator over half-open time intervals `[start, end)`.

### Parameters
- `requests`: a list of dicts, each with:
  - `"id"` (`str`): unique request identifier.
  - `"start"` (`int`): meeting start time (`>= 0`).
  - `"end"` (`int`): meeting end time.
  - `"priority"` (`int`): higher number means higher importance (can be negative, zero, or positive).
- `max_rooms` (`int`): maximum number of rooms available, numbered `1` through `max_rooms`.
- `turnaround` (`int`): non-negative cleaning/setup buffer time required after every scheduled meeting in the same room before the next meeting can start in that room.

### Validation
Raise `ValueError` before scheduling if:
- `max_rooms < 1` or `turnaround < 0`.
- Any request has `start < 0` or `end <= start`.
- Duplicate `"id"` values exist in `requests`.

### Scheduling Rules
1. **Processing Order**: Process requests one by one in the following greedy order:
   - Earlier `"start"` time first (`start` ascending).
   - Higher `"priority"` first (`priority` descending).
   - Shorter duration (`end - start` ascending).
   - Lexicographically smaller `"id"` (`id` ascending).
2. **Compatibility in a Room**: Because intervals are half-open and each scheduled meeting requires `turnaround` buffer time afterward, two meetings `[s1, e1)` and `[s2, e2)` (with `s1 <= s2`) can share a room if and only if `e1 + turnaround <= s2`.
3. **Room Choice**: When scheduling a request `[start, end)`:
   - Among existing open rooms (`1 .. current_open_rooms`) where the request is compatible with all meetings already assigned to that room, pick the room that becomes free **latest** (i.e. maximum `last_end + turnaround <= start`, tightest fit). If multiple existing rooms tie for the latest available time, pick the one with the **smallest room number**.
   - If no existing open room can accommodate the request, open a new room (assigned the next number `current_open_rooms + 1`) if `current_open_rooms < max_rooms`.
   - If no existing room fits and `current_open_rooms == max_rooms`, the request is **rejected**.

### Return Value
Return a dict with three keys:
- `"assignments"`: list of `[request_id, room_number]` pairs for all accepted requests, sorted chronologically by the request's `(start, end, room_number, request_id)` ascending.
- `"rejected"`: list of `request_id` strings for all rejected requests, sorted lexicographically (`id` ascending).
- `"rooms_used"`: integer count of distinct rooms used (`0` if no requests were accepted).

### Example
```python
allocate_rooms(
    [
        {"id": "m1", "start": 10, "end": 20, "priority": 1},
        {"id": "m2", "start": 20, "end": 30, "priority": 1},
        {"id": "m3", "start": 25, "end": 35, "priority": 2},
    ],
    max_rooms=1,
    turnaround=5,
)
# Returns:
# {
#   "assignments": [["m1", 1], ["m3", 1]],
#   "rejected": ["m2"],
#   "rooms_used": 1,
# }
```
