Fix `run(ops)` in `solution.py`.

`run(ops)` processes a stream of integer trade events into fixed-size OHLC bars using a watermark and lateness threshold. `ops` must be a list of operation dicts. It returns a list of emitted bar dicts.

Every op dict must have exactly the listed keys; missing or extra keys are invalid. “Integer” means a Python `int`, not `bool`. There is no sign restriction on `t`, `price`, or `seq`.

Operations:
- The first op must be `{"op": "config", "bucket": int, "lateness": int}` with `bucket >= 1` and `lateness >= 0`.
- `{"op": "event", "t": int, "price": int, "seq": int}` adds a trade event. Its bar index is `t // bucket` using Python floor division.
- `{"op": "watermark", "t": int}` advances the watermark to `max(current_watermark, t)`. Initially there is no watermark.
- `{"op": "end"}` advances the watermark to infinity and must be the final op.

Late-event rule: when an event is processed, it is accepted iff there is no current watermark or `t >= watermark - lateness`. Otherwise it is ignored and never stored.

Emission rule: after each `watermark` op, emit every buffered bar whose close time `(bar_index + 1) * bucket` satisfies `close_time + lateness <= watermark`. Emit bars in increasing `bar_index` order and remove them from the buffer. At `end`, emit all remaining buffered bars in increasing `bar_index` order. A bar with no accepted events is never emitted. If there is no `end`, bars still buffered when `run` returns are not emitted.

When a bar is emitted, sort its accepted events by `(t, seq, arrival_index)`, where `arrival_index` is the zero-based index of the event op in the original `ops` list. The emitted dict has exactly these keys:
- `bar`: the bar index
- `open`, `high`, `low`, `close`: from the sorted events; `high`/`low` are max/min price
- `volume`: number of accepted events in the bar
- `first_seq`, `last_seq`: `seq` of the first and last sorted events

Invalid inputs:
- If `ops` is not a list, raise `TypeError`.
- For all other malformed inputs, raise `ValueError`: empty `ops`, invalid first config, unknown op, duplicate config, missing/extra keys, wrong types, `end` not last, or ops after `end`.

Examples:
`run([{"op": "config", "bucket": 10, "lateness": 0}, {"op": "event", "t": 0, "price": 5, "seq": 1}, {"op": "event", "t": 9, "price": 7, "seq": 2}, {"op": "watermark", "t": 20}])` returns `[{"bar": 0, "open": 5, "high": 7, "low": 5, "close": 7, "volume": 2, "first_seq": 1, "last_seq": 2}]`.

`run([{"op": "config", "bucket": 5, "lateness": 2}, {"op": "event", "t": 0, "price": 3, "seq": 1}, {"op": "watermark", "t": 7}])` returns `[{"bar": 0, "open": 3, "high": 3, "low": 3, "close": 3, "volume": 1, "first_seq": 1, "last_seq": 1}]` because `5 + 2 == 7`.
