Fix `option_summary(options)` in `solution.py`. Return a two-element
list: a comma-space joined summary and a Boolean indicating whether
any option starts with '/'. Options start with '-', '--', or '/'. Put
one-character prefixes before double dashes, preserving input order
within each group. Do not remove duplicates or treat a slash in an
option's name as a prefix. An empty input returns ["", false].
