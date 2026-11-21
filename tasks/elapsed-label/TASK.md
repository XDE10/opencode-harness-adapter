Fix `elapsed_label(seconds)` in `solution.py`. Format a finite signed
number of seconds as MM:SS, or H:MM:SS when the magnitude is at least one
hour. Truncate the magnitude to whole seconds. Prefix a minus sign if
the original input is strictly negative, including a negative magnitude
smaller than one second. Minutes and seconds are two digits; hours are
not zero-padded. Preserve the function signature.
