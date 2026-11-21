# Build a clipped wait schedule

Fix `wait_schedule(count, initial, cap, budget)` in `solution.py`.

All four inputs are nonnegative integers. Produce at most count waits.
The planned wait at index i is initial times 2 to the power i, capped
at cap. A positive wait exceeding the remaining total budget is
clipped to that remainder. Stop before the first wait with no budget
remaining. If a planned wait is zero while budget is positive, keep
it as an entry.
