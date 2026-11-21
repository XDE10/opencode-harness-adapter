# Preserve explicit breaks when wrapping text

Fix `wrap_lines(text, width)` in `solution.py`.

Return a list of output lines for a positive width measured in Python
string characters. Split the input at each newline, preserving even
empty leading, interior and trailing lines. Within each input line,
collapse other whitespace runs to one space and greedily pack whole
words. A word wider than width is emitted whole on its own line.
A whitespace-only input line yields an empty string.
