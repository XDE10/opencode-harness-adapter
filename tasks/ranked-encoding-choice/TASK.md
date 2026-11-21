# Select the strongest encoding suggestion

Fix `choose_encoding(candidates, threshold)` in `solution.py`.

Each candidate is a pair of an encoding name (a string or null) and a
confidence (a number from 0 to 1 or null). Ignore missing or empty
names and missing confidence. Among candidates meeting or exceeding
threshold, choose the name with the highest confidence. Break ties
in favor of the earliest candidate. Return null when none qualify.
