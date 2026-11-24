Fix `fold_expr(node)` in `solution.py`.

Implement a deterministic constant-folding and dead-branch-pruning pass over a JSON-compatible expression AST. The function receives one node and returns a new folded node; it must not mutate the input.

Node forms:
- Literal: `{"kind": "lit", "value": v}`, where `v` is an `int`, `bool`, `str`, or `None`. Any other literal value raises `ValueError`.
- Variable: `{"kind": "var", "name": s}`, where `s` is a string. A non-string name raises `ValueError`.
- Unary: `{"kind": "not", "expr": node}` or `{"kind": "neg", "expr": node}`.
- Binary: `{"kind": "bin", "op": op, "left": node, "right": node}` with `op` one of `+`, `-`, `*`, `//`, `==`, `and`, `or`. Any other op raises `ValueError`.
- Conditional: `{"kind": "if", "cond": node, "then": node, "else": node}`.

Any node that is not a dict, or whose `kind` is unknown, raises `ValueError`.

Rules:
- Recursively fold children unless a rule says a child must not be folded.
- Literal truthiness: `None` is false; a bool uses its value; an int is false only when `0`; a string is false only when `""`.
- `not` folds to a bool literal when its operand folds to a literal.
- `neg` folds only for non-bool integer literals; otherwise keep the `neg` node.
- For `+`, `-`, `*`, `//`, fold only when both operands are non-bool integer literals. `//` uses Python floor division. A live division by zero raises `ZeroDivisionError`.
- For `==`, fold only when both operands are literals. Equality is exact by JSON type and value: booleans are distinct from integers, so `true == 1` folds to `false` and `false == 0` folds to `false`.
- For `and` / `or`, if the folded left operand is a literal that determines the result, return that determining literal and do not fold the right operand at all. Specifically: false left for `and` returns the left literal; true left for `or` returns the left literal; otherwise fold the right operand and return it. If the left operand is not a literal, fold the right operand and keep the binary node.
- For `if`, if the folded condition is a literal, fold and return only the selected branch; the unselected branch must not be folded at all. If the condition is not a literal, fold both branches and keep the `if` node.

Returned nodes must use exactly the shapes shown above.

Examples (JSON notation):
`fold_expr({"kind":"bin","op":"+","left":{"kind":"lit","value":2},"right":{"kind":"lit","value":3}})` returns `{"kind":"lit","value":5}`.

`fold_expr({"kind":"if","cond":{"kind":"lit","value":true},"then":{"kind":"lit","value":7},"else":{"kind":"bin","op":"//","left":{"kind":"lit","value":1},"right":{"kind":"lit","value":0}}})` returns `{"kind":"lit","value":7}`; the dead `else` branch is not evaluated.
