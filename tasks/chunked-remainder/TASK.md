Fix `chunked_list(items, size, strict=False)` in `solution.py`.
Split the input list into consecutive chunks of the given positive integer size as a list of
lists, keeping input order. A final shorter chunk is valid by default.
In strict mode, raise ValueError if a final chunk would be short. Also
raise ValueError for any nonpositive size, even if items is empty.
Keep the function name and parameters.
