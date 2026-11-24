Fix `run(ops)` in `solution.py`.

Implement a deterministic job retry state machine. `ops` is a list of operation dictionaries processed in the given order. Each operation has `op` (a string) and `t` (a nonnegative integer). `t` values may repeat and are not required to be globally increasing. Return a list of strings, one per successfully processed operation. If any operation is invalid, raise `ValueError` immediately; no partial list is returned.

Each job is either active or terminal (`done`, `failed`, `cancelled`). An active job stores `attempts`, `due`, `base`, `factor`, and `max_attempts`. `job` must be a nonempty string. `base`, `factor`, and `max_attempts` must be positive integers. Bool is not accepted for integer fields. Missing or invalid fields, unknown op names, negative `t`, and non-dict operations raise `ValueError`. Extra fields are ignored.

Operations:
- `submit`: requires `job`, `base`, `factor`, `max_attempts`. If that job is currently active, raise `ValueError`. If it is terminal/cancelled, replace it with a fresh active job: `attempts = 0`, `due = t`. Append `"submitted"`.
- `run`: requires `job`. If the job is unknown or not active, raise `ValueError`. If `t < due`, append `"waiting"` and do not change state. Otherwise increment `attempts`. If `attempts >= max_attempts`, set the job to `failed` and append `"failed"`. Otherwise set `due = t + base * factor ** (attempts - 1)` and append `"retry"`.
- `succeed`: requires `job`. If the job is unknown or not active, raise `ValueError`. If `t < due`, append `"waiting"` and do not change state. Otherwise set the job to `done` and append `"done"`.
- `cancel`: requires `job`. If the job is unknown or not active, raise `ValueError`. Otherwise set it to `cancelled` and append `"cancelled"`.
- `status`: requires `job`. If the job is unknown, raise `ValueError`. If terminal/cancelled, append that state. If active, append `"waiting"` when `t < due`, otherwise append `"ready"`.

Examples:
`run([{"op": "submit", "t": 0, "job": "a", "base": 2, "factor": 2, "max_attempts": 3}, {"op": "run", "t": 0, "job": "a"}, {"op": "status", "t": 2, "job": "a"}])` returns `["submitted", "retry", "ready"]`.

`run([{"op": "submit", "t": 0, "job": "b", "base": 1, "factor": 2, "max_attempts": 1}, {"op": "run", "t": 0, "job": "b"}])` returns `["submitted", "failed"]`.
