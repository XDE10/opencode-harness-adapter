Fix `shift_month(year, month, day, delta)` in `solution.py`.
Add the signed number of calendar months to a valid Gregorian date.
Normalize the year/month across year boundaries. Keep the day unless
it exceeds the target month's length, then clamp to that month's last
day. Use Gregorian leap-year rules. Inputs and results stay in years
1 through 9999. Return [year, month, day].
