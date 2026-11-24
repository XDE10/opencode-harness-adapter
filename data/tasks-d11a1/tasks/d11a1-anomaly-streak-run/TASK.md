Fix `run(ops)` in `solution.py`.

Implement a deterministic per-metric anomaly streak detector. The grader calls `run(ops)` with one positional argument: a list of operation dicts. Process operations in order and return a list with one result per operation.

Constants are fixed: anomaly threshold `10`, idle gap `5`, streak need `2`.

Operation schemas:
- `{"op": "observe", "metric": str, "t": int, "value": int}`
- `{"op": "reset", "metric": str}`
- `{"op": "status", "metric": str}`

You may assume required keys exist and have the stated types. If `op` is any other string, raise `ValueError`.

State is independent for each metric. Each metric tracks `prev`, `last_t`, `streak`, and `emitted`.

Rules:
- The first observation for a metric is never anomalous; it starts a segment with `streak = 0`, `emitted = False`, `prev = value`, and `last_t = t`.
- Before comparing a new observation, if `t - last_t > 5`, the idle gap splits the segment: clear `streak` and `emitted`, set `prev = value` and `last_t = t`, append `None`, and do not treat the sample as anomalous. An exact gap of `5` does not split the segment.
- Without a split, a sample is anomalous iff `abs(value - prev) > 10`. Equality with `10` is normal.
- On an anomalous sample, increment `streak`. When `streak >= 2` and `emitted` is false, append `{"metric": metric, "t": t, "streak": streak}` and set `emitted = True`. Further anomalies in the same streak append `None`.
- On a normal sample, set `streak = 0` and `emitted = False`, then append `None`. This allows a later new streak to emit again.
- After every non-split anomalous or normal comparison, update `prev = value` and `last_t = t`.
- `reset` removes all state for that metric and appends `None`; resetting an unknown metric is a no-op. The next observation is a first observation.
- `status` appends `{"streak": s, "emitted": b, "prev": p}`, where `p` is the last processed value or `None` if there is no state. `status` does not mutate state.

Examples:
`run([{"op": "observe", "metric": "cpu", "t": 0, "value": 0}, {"op": "observe", "metric": "cpu", "t": 1, "value": 20}, {"op": "observe", "metric": "cpu", "t": 2, "value": 40}])` returns `[None, None, {"metric": "cpu", "t": 2, "streak": 2}]`.

`run([{"op": "observe", "metric": "a", "t": 0, "value": 0}, {"op": "observe", "metric": "a", "t": 1, "value": 20}, {"op": "observe", "metric": "a", "t": 6, "value": 40}, {"op": "status", "metric": "a"}])` returns `[None, None, {"metric": "a", "t": 6, "streak": 2}, {"streak": 2, "emitted": true, "prev": 40}]`.
