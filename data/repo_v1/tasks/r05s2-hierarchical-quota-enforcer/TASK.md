# Issue Report: Hierarchical Quota Enforcer Policy Resolution & Transactional Rollback Bugs

## Context
`r05s2quota` provides an in-memory multi-tenant rate and quota service supporting hierarchical tenant paths (e.g. `org`, `org/team`, `org/team/user`) and transactional multi-step quota checks.

## Behavioral Specification

### 1. Policy Resolution & Conflict Resolution (`policies.py`)
- Each `QuotaPolicy` has:
  - `scope`: hierarchical path string (e.g. `"acme"`, `"acme/payments"`, `"acme/payments/svc-a"`).
  - `metric`: resource identifier (e.g. `"api_calls"`, `"tokens"`).
  - `limit`: integer maximum capacity in the sliding window.
  - `window_seconds`: integer sliding window duration (`> 0`).
  - `priority`: integer priority used to break ties when multiple policies are registered for the **same** `(scope, metric)`.
- `PolicyRegistry.register(policy)`:
  - When multiple policies are registered for the **same** `(scope, metric)`, the registry must keep only the winning policy according to:
    1. Highest `priority` wins.
    2. If `priority` is tied, the **most restrictive** policy wins (lowest `limit / window_seconds` rate; if rates are equal, lowest `limit`).
- `PolicyRegistry.resolve_chain(scope, metric)`:
  - Given a target `scope` like `"acme/payments/svc-a"`, returns the list of active policies for `metric` along the ancestor chain from root-most to leaf-most (`"acme"`, then `"acme/payments"`, then `"acme/payments/svc-a"`), skipping any ancestor levels that have no registered policy for `metric`.

### 2. Sliding-Window Store (`store.py`)
- `SlidingWindowStore` tracks timestamped consumption events `(timestamp, amount)` per `(scope, metric)` key.
- Events within `[now - window_seconds + 1, now]` (inclusive) count toward active usage for a policy with `window_seconds`.
- For example, with `window_seconds = 10` and `now = 100`, events at `t = 90` (`100 - 10 = 90`) have aged out, while events in `[91, 100]` are active.

### 3. Hierarchical Enforcer & Multi-Step Atomic Acquisition (`enforcer.py`)
- `QuotaEnforcer.acquire(scope, metric, amount, now)`:
  - Resolves all applicable policies along the ancestor chain for `(scope, metric)`.
  - If no policies exist in the chain, the request is allowed (`allowed=True`, `violated_scope=None`, `remaining={}`).
  - Checks whether adding `amount` at timestamp `now` would exceed `policy.limit` for **any** policy in the ancestor chain.
  - If all ancestor policies can accommodate `amount`, records `amount` at `now` for **each** policy's `(policy.scope, metric)` in the store and returns `AcquireResult(allowed=True, violated_scope=None, remaining={p.scope: p.limit - new_usage})`.
  - If **any** policy in the chain would be exceeded, **no** consumption may remain recorded in any ancestor scope (atomic rollback), and `AcquireResult(allowed=False, violated_scope=first_failing_policy.scope, remaining=...)` is returned (where `remaining` maps each resolved policy's scope to its current remaining capacity before the failed request, clamped to `>= 0`).
- `QuotaEnforcer.acquire_batch(requests, now)`:
  - Accepts a sequence of `(scope, metric, amount)` tuples executed as an all-or-nothing transaction at timestamp `now`.
  - Processes requests in order. Note that later requests in the same batch may share ancestor scopes with earlier requests in the batch and must see the cumulative usage from earlier steps in the batch!
  - If every step succeeds, returns the list of `AcquireResult` objects from each step.
  - If any step fails, **all** earlier steps from the batch must be rolled back completely so store state is unchanged, and `acquire_batch` stops at the first failing step and returns the results collected so far (ending with the failed `AcquireResult`).
- `QuotaEnforcer.invalidate_subtree(root_scope, metric=None)`:
  - Clears recorded usage in the store for `root_scope` and all descendant scopes under `root_scope/` (e.g. invalidating `"acme"` clears `"acme"` and `"acme/payments"`, `"acme/payments/svc-a"`, etc., but **must not** clear sibling scopes that merely share a string prefix like `"acme_corp"` or `"acme-2"`).
  - If `metric` is provided, only entries for that metric are cleared; if `metric is None`, entries for all metrics in that subtree are cleared.

## Reported Symptoms
1. Registering a lower-priority or less-restrictive policy at the same `(scope, metric)` overwrites an existing higher-priority or more-restrictive policy, and tie-breaking on equal priority picks the higher limit instead of the most restrictive policy.
2. When a hierarchical `acquire` fails at a deeper scope (or a multi-step `acquire_batch` fails partway through), ancestor/earlier consumption is not properly rolled back, and `invalidate_subtree("acme")` accidentally wipes unrelated tenants like `"acme_corp"`.
