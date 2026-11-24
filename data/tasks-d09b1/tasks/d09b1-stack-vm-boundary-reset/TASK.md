Fix `run(ops)` in `solution.py`.

`run(ops)` executes a tiny stack bytecode VM. `ops` is a list of instruction dicts, and the function returns a dict with exactly these keys:
- `"stack"`: list of integers, top of stack last.
- `"vars"`: dict from variable name to integer value.
- `"out"`: list of integers printed by `print`.
- `"steps"`: integer count of every fetched instruction, including `halt`.

The program counter starts at `0`. Execution stops when `halt` runs or when `pc` is outside `0 <= pc < len(ops)`. A `target` field must be an integer with `0 <= target <= len(ops)`. All integer fields must be Python `int`; `bool` is not accepted. Missing/invalid fields, unknown op names, stack underflow, and `ret` with an empty call stack raise `ValueError`.

Instructions:
- `{"op": "push", "v": int}`: append `v` to the stack.
- `{"op": "load", "name": str}`: append `vars.get(name, 0)`.
- `{"op": "store", "name": str}`: pop a value and store it under `name`.
- `{"op": "add"|"sub"|"mul"}`: pop `b`, then `a`, then push `a + b`, `a - b`, or `a * b`.
- `{"op": "print"}`: pop a value and append it to `out`.
- `{"op": "jmp", "target": int}`: set `pc` to `target`.
- `{"op": "jz", "target": int}`: validate `target`, pop the condition, and set `pc` to `target` only when the condition equals `0`; otherwise continue.
- `{"op": "call", "target": int}`: push the instruction immediately after the `call` onto the call stack, then set `pc` to `target`.
- `{"op": "ret"}`: pop the call stack and set `pc` to the popped return address.
- `{"op": "reset"}`: clear `stack`, `vars`, `out`, and the call stack; continue at the next instruction. It does not reset `pc` or `steps`.
- `{"op": "halt"}`: stop execution.

Examples:
`run([{"op": "push", "v": 2}, {"op": "push", "v": 3}, {"op": "add"}, {"op": "print"}, {"op": "halt"}])` returns `{"stack": [], "vars": {}, "out": [5], "steps": 5}`.

`run([{"op": "call", "target": 3}, {"op": "halt"}, {"op": "push", "v": 99}, {"op": "ret"}])` returns `{"stack": [99], "vars": {}, "out": [], "steps": 4}`.
