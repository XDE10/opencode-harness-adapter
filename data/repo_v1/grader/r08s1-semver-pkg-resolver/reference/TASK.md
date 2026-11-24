# Issue Report: Incorrect Caret Constraint Expansion for `0.x.y` and Stale Transitive Constraints During Backtracking

## Summary
Users of `r08s1pkg` are hitting two resolution issues in production lockfile builds:
1. **Zero-major caret constraints (`^0.minor.patch` and `^0.0.patch`)** match versions across breaking `0.x` boundaries instead of locking the left-most non-zero version segment according to standard SemVer caret semantics.
2. **Transitive constraints from backtracked candidates leak into subsequent branches**: When a high-version candidate of package `A` fails due to a downstream conflict and the resolver backtracks to try an older candidate of `A`, transitive requirements introduced by the rejected candidate remain active and cause false `ResolutionConflictError`s or overly restricted downstream choices.

## Expected Specification

### 1. SemVer Parsing & Comparison (`r08s1pkg.semver`)
- Versions have integer components `(major, minor, patch)`, e.g. `"1.2.3"`.
- Supported constraint tokens (comma-separated in a spec string, all must hold):
  - `*` (matches any version)
  - `=X.Y.Z` or `X.Y.Z` (exact match)
  - `>=X.Y.Z`, `>X.Y.Z`, `<=X.Y.Z`, `<X.Y.Z`
  - `~X.Y.Z`: allows patch-level changes: `>=X.Y.Z` and `<X.(Y+1).0`
  - `^X.Y.Z`: allows changes that do not modify the left-most non-zero digit in `(major, minor, patch)`:
    - If `major > 0`: `>=X.Y.Z` and `<(X+1).0.0`
    - If `major == 0` and `minor > 0`: `>=0.Y.Z` and `<0.(Y+1).0`
    - If `major == 0` and `minor == 0`: `>=0.0.Z` and `<0.0.(Z+1)`

### 2. Dependency Resolution & Lockfile Planning (`r08s1pkg.resolver`)
- `Registry` stores available `Release(name, version, dependencies)` entries where `dependencies` maps `dep_name -> SpecSet`.
- `LockPlanner.resolve(root_requirements: dict[str, str]) -> dict[str, Version]`:
  - Resolves all direct and transitive dependencies so that every selected package version satisfies **all** active constraints from the root and from every selected package that depends on it.
  - Always prefers higher versions first (descending `Version` order) for any package being resolved.
  - When a candidate version leads to an unsatisfiable downstream constraint, the planner must backtrack cleanly—restoring both selected versions and accumulated constraints to the exact state prior to trying that candidate—before attempting the next lower candidate version.
  - If an already-selected packagelater receives an additional constraint from another branch that the currently selected version does not satisfy, that branch is invalid and must backtrack.
  - If no valid assignment exists, raise `ResolutionConflictError`.
