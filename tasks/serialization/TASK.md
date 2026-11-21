Fix `encode_record(record)` in `solution.py`. Return compact JSON as a string,
with object keys sorted at every depth, no separator whitespace, and Unicode
characters left unescaped when JSON permits. Preserve array order. Reject
NaN and either infinity anywhere in the input by raising ValueError.
Inputs are dictionaries of JSON-shaped values with string keys.
Keep the public function signature.
