Fix `compact_size(value, binary=False)` in `solution.py`. The input is a
signed 64-bit integer count of bytes. Select decimal units (B, kB, MB, GB with
base 1000) or binary units (B, KiB, MiB, GiB with base 1024). Display bytes
without a decimal, all larger units with one decimal, and a single space
before the units. Keep the sign for negative values. When the displayed
mantissa rounds to the base and a larger unit exists, promote the unit
and format the original value in that unit. The largest unit never promotes.
