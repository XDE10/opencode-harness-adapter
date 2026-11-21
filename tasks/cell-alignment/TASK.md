Fix `align_cell(text, width, alignment)` in `solution.py`.
The input is a single printable ASCII field, the desired nonnegative
width, and one of 'l', 'r', or 'c'. Pad using spaces on the appropriate
side. For centered text, put any extra space on the right. If text
already occupies the requested width or more, return it unchanged.
