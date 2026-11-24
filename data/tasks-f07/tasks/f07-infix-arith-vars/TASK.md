Fix `eval_infix(expr, env=None)` in `solution.py`.

Evaluate an integer infix arithmetic expression `expr` using optional variable bindings `env` (mapping `str -> int`, defaulting to `{}`).

Supported tokens and rules:
- Whitespace is ignored.
- Literals: non-negative base-10 integer literals.
- Identifiers: `[A-Za-z_][A-Za-z0-9_]*`, looked up in `env` (`KeyError` if missing).
- Operators by precedence (lowest to highest):
  1. Binary `+`, `-` (left-associative)
  2. Binary `*`, `//`, `%` (left-associative, Python floor division and modulo; `ZeroDivisionError` on divisor `0`)
  3. Unary `+`, `-` (right-associative, stackable such as `--x`; binds looser than `^`, so `-2 ^ 2 == -4`)
  4. Binary `^` (right-associative integer exponentiation, so `2 ^ 3 ^ 2 == 512`; negative exponent raises `ValueError`)
  5. Parenthesized expressions `(expr)`

Raise `ValueError` on empty expressions, unknown characters, mismatched parentheses, missing operands, trailing tokens, or negative exponents.

Example:
```python
eval_infix("-(a + b) ^ 2 + 1", {"a": 1, "b": 2})  # -> -8
```
