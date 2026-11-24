# Issue Report: Multi-Tenant Hierarchical Rate & Quota Enforcer

## Background
The `quotaguard` package implements a deterministic multi-tenant hierarchical rate and quota enforcement service. Policies are parsed from plain specification strings (e.g., `"120/m burst=150"` or `"3600/h"`) and attached to tenants or parent organizations. When a request arrives for a tenant, `QuotaEnforcer.check_and_consume(tenant_id, cost, now)` evaluates the hierarchy (from root ancestor down to the leaf tenant) against a stateful `TokenBucketStore`.

## Reported Symptoms
1. **Throughput miscalculation on non-second rate windows**: Policies configured with minute (`/m`) or hour (`/h`) units refill tokens far faster than expected (acting as if the entire capacity refills every second rather than over 60 or 3600 seconds), whereas `/s` policies behave normally. Additionally, when `burst=...` is omitted from a policy string, `burst_capacity` should default to `limit`, and explicit `burst` values smaller than `limit` must raise `ValueError`.
2. **Parent quota leaked when leaf tenant rejects a request**: In a multi-level hierarchy (e.g. `org-a` -> `team-1`), when a request has enough tokens at the parent (`org-a`) level but is rejected at the child (`team-1`) level, the parent's tokens are still permanently deducted! Hierarchical enforcement must be transactional across the ancestor chain: either all scopes in the tenant's lineage have sufficient tokens and all are deducted, or the request is rejected (`allowed=False`) and **no** scope in the lineage loses tokens (though time-based refills up to `now` still apply).

## Behavioral Specification
- **`parse_policy(name: str, spec: str) -> RatePolicy`**:
  - Parses `<limit>/<unit>` with an optional `burst=<int>` token (whitespace-separated), where `<unit>` is one of `s` (1 second), `m` (60 seconds), or `h` (3600 seconds).
  - `RatePolicy.refill_rate_per_sec` must equal `limit / window_seconds` (as a `float`).
  - `RatePolicy.burst_capacity` defaults to `float(limit)` if `burst=` is not provided. If `burst` is provided and `burst < limit`, or `limit <= 0`, `parse_policy` must raise `ValueError`.
- **`TokenBucketStore`**:
  - Tracks per-scope `(policy.name, scope_id)` token buckets initialized at `policy.burst_capacity` at the first seen timestamp `now`.
  - Refills accrued tokens by `max(0.0, now - last_ts) * policy.refill_rate_per_sec`, capped at `policy.burst_capacity`, and updates `last_ts = max(last_ts, now)`.
- **`QuotaEnforcer`**:
  - `register_tenant(tenant_id, policy, parent_id=None)` registers a tenant and its optional parent.
  - `check_and_consume(tenant_id, cost=1.0, now=0.0) -> QuotaDecision`:
    - Resolves the lineage from root ancestor to `tenant_id`.
    - Refills all buckets in the lineage to timestamp `now`.
    - Checks whether every bucket in the lineage has `available_tokens >= cost`.
    - If **all** scopes in the lineage can afford `cost`, deducts `cost` from each scope in the lineage and returns `QuotaDecision(allowed=True, blocked_by=None, remaining_min=min_remaining_across_lineage)`.
    - If **any** scope in the lineage cannot afford `cost`, deducts tokens from **none** of the scopes, and returns `QuotaDecision(allowed=False, blocked_by=first_failing_scope_id, remaining_min=0.0)` where `first_failing_scope_id` is the highest ancestor (in root-to-leaf order) that lacked sufficient tokens.
