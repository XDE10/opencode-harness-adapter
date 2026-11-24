Fix `analyze_sessions(events, idle_gap, threshold)` in `solution.py`.

Implement a deterministic log-session analyzer.

Inputs:
- `events`: a list of dicts. Each event must have exactly these keys: `{"user": str, "t": int, "seq": int, "value": int}`. Here `int` means a Python `int`, not `bool`.
- `idle_gap`: a positive `int`.
- `threshold`: an `int`.

Raise `ValueError` if any input violates these types or shapes, including missing or extra event keys. Do not mutate `events`.

Processing:
- Group events by `user`.
- For each user, sort events by `(t, seq, original_input_index)`. The original input index is the event's index in the original `events` list and breaks any remaining ties.
- Start a new session for the first event of a user or when `t - previous_t > idle_gap`, where `previous_t` is the immediately preceding event's `t` in sorted order. A gap exactly equal to `idle_gap` stays in the same session.
- Each session summary is a dict with exactly these keys: `start`, `end`, `count`, `max_streak`, `peak`.
  - `start` and `end` are the first and last `t` values in that session.
  - `count` is the number of events in that session.
  - `peak` is the maximum `value` in that session.
  - An event is anomalous iff `value > threshold` strictly. `max_streak` is the longest run of consecutive anomalous events within one session. A non-anomalous event resets the streak, and every session boundary resets the streak.

Return a dict mapping each user to its list of session summaries, with sessions ordered by session start. Users with no events are absent. An empty `events` list returns `{}`.

Example:
`analyze_sessions([{"user": "a", "t": 0, "seq": 0, "value": 4}, {"user": "a", "t": 2, "seq": 1, "value": 6}, {"user": "a", "t": 3, "seq": 2, "value": 7}], 2, 5)`
returns `{"a": [{"start": 0, "end": 3, "count": 3, "max_streak": 2, "peak": 7}]}`.
