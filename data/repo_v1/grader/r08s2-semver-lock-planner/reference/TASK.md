# Issue Report: Caret `^0.x.y` Constraint Bounds & Lockfile Backtracking State Mutation

## Context
`r08s2pkg` implements an in-memory Semantic Versioning (`major.minor.patch`) dependency resolver and lockfile planner. Given a `PackageRegistry` containing release manifests and a set of root package requirements, `LockfilePlanner.resolve(roots)` finds the highest compatible version assignment for all required packages using deterministic backtracking search.

## Reported Failures
Two production issues have been reported by teams resolving complex dependency graphs:

1. **Pre-1.0 Caret Constraints (`^0.y.z` and `^0.0.z`) Over-Match Breaking Releases**:
   According to Cargo / npm semver caret rules:
   - `^M.m.p` where `M > 0` allows `>=M.m.p <(M+1).0.0`.
   - `^0.m.p` where `m > 0` must lock the minor version: `>=0.m.p <0.(m+1).0`.
   - `^0.0.p` must lock the exact patch version: `>=0.0.p <0.0.(p+1)` (or `==0.0.p`).
   Currently, caret constraints on `0.x.y` releases allow incompatible minor/major upgrades up to `<1.0.0`.

2. **Backtracking Leaves Stale Transitive Dependencies and Mutated Constraints in Lockfile Plans**:
   When `LockfilePlanner.resolve()` picks a candidate version for package `A` that pulls in a transitive dependency `T` (or adds constraints onto another package `B`), and a downstream conflict forces the solver to backtrack to an older version of `A` (which either drops `T` or imposes a different constraint on `B`):
   - Constraints collected from the abandoned version of `A` remain active or corrupt the shared constraint state.
   - Packages introduced only by the abandoned candidate branch can leak into the final resolved lockfile even if the chosen branch no longer depends on them.

## Behavioral Specification
- `Version.parse("M.m.p")` parses non-negative integers `major`, `minor`, `patch` and supports total ordering.
- `ConstraintSpec.parse(expr)` parses comma-separated clauses (`>=`, `<=`, `>`, `<`, `==`, `!=`, `~M.m.p`, `^M.m.p`, or `*`).
  - `~M.m.p` allows `>=M.m.p <M.(m+1).0`.
  - `^M.m.p` follows standard zero-major semver rules (`M > 0` -> `<(M+1).0.0`; `M == 0, m > 0` -> `<0.(m+1).0`; `M == 0, m == 0` -> `<0.0.(p+1)`).
- `LockfilePlanner.resolve(root_requirements: dict[str, str]) -> dict[str, str]`:
  - Prefers higher versions first (lexicographically by package name for deterministic branching).
  - Returns a dictionary mapping *only* reachable required package names to their resolved version strings (`"M.m.p"`), sorted by package name.
  - Raises `ResolutionConflictError` if no valid assignment satisfies all root and active transitive constraints.
