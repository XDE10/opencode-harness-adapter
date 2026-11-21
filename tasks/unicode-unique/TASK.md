Fix `unique_labels(labels, ignore_case=False)` in `solution.py`.
Return each distinct string once, preserving its first spelling and its
position relative to the other retained strings. With ignore_case on,
compare using Unicode casefolding. Do not trim whitespace or normalize
other aspects of the strings. The input is a list of strings.
