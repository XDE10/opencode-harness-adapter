# Issue Report: Multi-Tenant Rate & Quota Service Mis-parsing Rate Windows and Rolling Back Partially on Hierarchical Denials

## Summary
Our multi-tenant rate and quota service (`r05s3pkg`) parses declarative policy DSL strings into `QuotaPolicy` instances and enforces them hierarchically across parent/child scopes (`global` -> `tenant:<id>` -> `user:<id>`).

In production we are seeing two distinct reliability bugs:
1. **Rate window specification parsing (`parse_policy_spec`)**: Policy specs written with minutes or hours (such as `"120/1m"` or `"3600/1h"`) are being enforced with the wrong effective token refill rate and sliding window duration, causing tenants with minute/hour windows to get throttled almost immediately as if their window were a fraction of the configured duration.
2. **Hierarchical transaction atomicity (`HierarchicalEnforcer.check_and_consume`)**: When a request passes the higher-level scope policies (e.g., `global` and `tenant:acme`) but is rejected by a deeper scope policy (e.g., `user:alice`), tokens/usage already consumed from the ancestor scopes are not remaining untouched—repeated failed requests from a single throttled user end up draining the shared `tenant` and `global` quota pools.

## Behavioral Specification

### 1. Policy Spec Parsing (`r05s3pkg.policy`)
- `parse_policy_spec(spec_dict)` accepts a dictionary with:
  - `name` (`str`): unique policy identifier
  - `scope` (`str`): target scope, e.g. `"global"`, `"tenant:acme"`, `"user:alice"`
  - `algorithm` (`str`): either `"token_bucket"` or `"sliding_window"`
  - `rate` (`str`): formatted as `"<limit>/<count><unit>"` or `"<limit>/<unit>"` where `<limit>` is a positive integer, optional `<count>` is a positive integer (defaults to `1` if omitted, e.g. `"100/m"` == `"100/1m"`), and `<unit>` is one of:
    - `"s"` -> `1.0` second
    - `"m"` -> `60.0` seconds
    - `"h"` -> `3600.0` seconds
    - `"d"` -> `86400.0` seconds
  - `burst` (`int`, optional): maximum bucket capacity for `token_bucket`. Defaults to `<limit>` when omitted or `None`. For `sliding_window`, `burst` equals `<limit>`.
- The resulting `QuotaPolicy` must have:
  - `limit`: integer `<limit>`
  - `window_seconds`: float total duration in seconds (`count * unit_seconds`)
  - `burst`: integer capacity (`<= 0` raises `ValueError`)
  - `refill_rate`: float tokens per second, defined as `limit / window_seconds`.
- Invalid rate format, non-positive `limit`/`count`/`burst`, or unknown `algorithm`/`unit` must raise `ValueError`.

### 2. Stateful Quota Stores (`r05s3pkg.stores`)
- `TokenBucketStore`:
  - Initializes untested keys at full `policy.burst` capacity at `now`.
  - Refills elapsed time `(now - last_ts) * policy.refill_rate` capped at `policy.burst` (clamping `now >= last_ts`).
  - Allows a request of `cost` iff available tokens `>= cost`.
- `SlidingWindowStore`:
  - Tracks `(timestamp, cost)` events within the active half-open window `(now - policy.window_seconds, now]`.
  - Events with `timestamp <= now - policy.window_seconds` are expired.
  - Allows a request of `cost` iff `current_window_usage + cost <= policy.limit`.

### 3. Hierarchical Enforcement (`r05s3pkg.enforcer`)
- `HierarchicalEnforcer.check_and_consume(scopes, cost=1, now=0.0)` evaluates all registered policies matching each scope in `scopes` in order.
- **All-or-nothing atomicity**:
  - If **every** matching policy across all requested `scopes` can satisfy `cost` at timestamp `now`, the enforcer commits the consumption of `cost` across all matching policies and returns `EnforcementResult(allowed=True, denied_by=None, retry_after=0.0, remaining_by_policy={...})`.
  - If **any** matching policy cannot satisfy `cost`, **no policy state in any scope may be mutated** (neither ancestor scopes nor earlier policies in the same scope). It returns `EnforcementResult(allowed=False, denied_by=failing_policy.name, retry_after=wait_seconds, remaining_by_policy={...})` reflecting the First failing policy in evaluation order.
