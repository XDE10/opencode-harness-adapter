Fix `run(ops)` in `solution.py`.

Implement a deterministic, stateful RBAC evaluator. `ops` is a list of operation dicts. `run` returns a list with one entry per operation: `null` for every operation except `check`, which appends a boolean. If an exception is raised, processing stops immediately and the exception propagates.

State:
- Policies are keyed by string `id`. Each policy has an `effect` (`"allow"` or `"deny"`), lists of role names, action glob patterns, resource glob patterns, and an `enabled` flag.
- Users have sets of roles. A user with no roles has an empty set.

Operations:
- `{"op": "add_policy", "id": str, "effect": str, "roles": [str], "actions": [str], "resources": [str]}`: add or replace the policy with this id and set it enabled. `effect` must be exactly `"allow"` or `"deny"`, otherwise raise `ValueError`.
- `{"op": "remove_policy", "id": str}`: remove the policy if present; absent id is a no-op.
- `{"op": "set_enabled", "id": str, "enabled": bool}`: set the policy's enabled flag to `bool(enabled)`. If the id is absent, raise `KeyError`.
- `{"op": "set_roles", "user": str, "roles": [str]}`: replace the user's role set exactly; an empty list clears all roles.
- `{"op": "add_role", "user": str, "role": str}`: add one role, creating the user's role set if needed.
- `{"op": "remove_role", "user": str, "role": str}`: remove one role if present; absent user or role is a no-op.
- `{"op": "check", "user": str, "action": str, "resource": str}`: evaluate access and append a boolean.

Evaluation rules for `check`:
- Only enabled policies are considered.
- A policy matches when the user has at least one listed role, `action` fully matches at least one action pattern, and `resource` fully matches at least one resource pattern. Empty role/action/resource lists therefore never match.
- Deny-overrides: if any enabled matching policy has effect `"deny"`, append `false`, even if allow policies also match. Otherwise append `true` if any enabled matching policy has effect `"allow"`. If no policy matches, append `false`. There is no priority by id or insertion order.
- Unknown `op` values raise `ValueError`. Missing required keys raise `KeyError`.

Glob matching is case-sensitive and matches the entire string. Only `*` and `?` are special: `*` matches zero or more characters except `/`; `?` matches exactly one character except `/`. All other characters, including backslash and regex metacharacters, are literal.

Example:
`run([{"op": "add_policy", "id": "p", "effect": "allow", "roles": ["reader"], "actions": ["read"], "resources": ["/docs/*"]}, {"op": "set_roles", "user": "u", "roles": ["reader"]}, {"op": "check", "user": "u", "action": "read", "resource": "/docs/a"}, {"op": "check", "user": "u", "action": "read", "resource": "/docs/a/b"}])` returns `[None, None, True, False]`.

Example:
An allow policy followed by a matching deny policy produces `false` for `check`, regardless of insertion order.
