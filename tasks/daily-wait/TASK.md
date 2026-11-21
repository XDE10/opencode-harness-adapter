# Calculate time until a daily slot

Fix `minutes_until(now, target, include_now=False)` in `solution.py`.

Both times are minutes after midnight (integers from 0 through 1439).
Return the wait to the next daily occurrence of target. When both times
are equal, return zero if include_now is true and a full day otherwise.
The day length is always 1440 minutes.
