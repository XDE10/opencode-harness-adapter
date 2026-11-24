Fix `eval_expr(expr, variables)` in `solution.py`.

Implement a deterministic integer expression evaluator.

- `expr` is a string containing whitespace, ASCII decimal integer literals, ASCII identifiers `[A-Za-z_][A-Za-z0-9_]*`, operators `+ - * /`, and parentheses. Whitespace is ignored. There is no implicit multiplication.
- `variables` is a dict mapping identifier strings to integers. A variable evaluates to its mapped integer; if the key is absent, raise `KeyError` with the variable name.
- Grammar/precedence: unary `+`/`-` bind tightest and may repeat; `*` and `/` bind next; `+` and `-` bind lowest. Binary `+`, `-`, `*`, and `/` are all left-associative.
- Binary `/` is Python-style floor division (`//`) on integers. Division by zero raises `ZeroDivisionError`.
- Parentheses override precedence.
- Invalid syntax (empty expression, unexpected token, unmatched or missing `)`, trailing tokens, invalid character) raises `ValueError`.
- Return an `int`.

Examples:
`eval_expr("1 + 2 * 3", {})` returns `7`.
`eval_expr("-7 / 2 + x", {"x": 10})` returns `6`, because `-7 / 2` is `-4`.
`eval_expr("10 - 3 - 2", {})` returns `5` because subtraction is left-associative.
