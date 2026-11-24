Fix `run_rpn(program, inputs=None)` in `solution.py`.

Execute a stack-based RPN bytecode program given as a string (tokens separated by whitespace; `#` starts a comment until the end of the line) with optional initial variables `inputs` (`dict[str, int]`, defaulting to `{}`).

Instructions:
- Integer literals (optional leading `+`/`-`): push integer onto the stack.
- `ADD`, `SUB`, `MUL`, `DIV` (`a // b`), `MOD` (`a % b`): pop `b`, then pop `a`, push `a op b` (`ZeroDivisionError` if `b == 0` in `DIV`/`MOD`).
- `DUP`: duplicate top of stack; `SWAP`: swap top two values; `DROP`: pop top; `OVER`: push a copy of the second value from top.
- `LOAD <name>`: push `vars[name]` (`KeyError` if `name` is not defined).
- `STORE <name>`: pop top of stack and bind `vars[name]`.
- `<label>:`: declare label pointing to the next instruction (`[A-Za-z_][A-Za-z0-9_]*`). Label declarations do not count as executed steps. Duplicate labels raise `ValueError`.
- `JMP <label>`: jump unconditionally to `<label>`.
- `JZ <label>`, `JNZ <label>`: pop top of stack and jump to `<label>` if `== 0` (`JZ`) or `!= 0` (`JNZ`).
- `HALT`: stop execution immediately (counts as 1 step).

Return `{"stack": <list[int]>, "vars": <dict[str, int]>, "steps": <int>}` without mutating the caller's `inputs` dict. Raise `ValueError` on unknown opcodes, missing instruction operands, unknown labels, duplicate labels, stack underflow, or exceeding `10000` executed steps.

Example:
```python
run_rpn("LOAD x 2 MUL 1 ADD", {"x": 5})  # -> {"stack": [11], "vars": {"x": 5}, "steps": 5}
```
