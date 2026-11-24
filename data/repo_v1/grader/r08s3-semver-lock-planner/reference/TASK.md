# Bug Report: Pre-release caret ranges and backtracked transitive constraints in `r08s3pkg`

## Summary
We found two issues in our internal semantic-version dependency resolver (`r08s3pkg`) during release planning:

1. **Pre-release (`0.x.y`) caret constraint expansion (`^0.x.y`)**:
   When parsing caret constraints for `0.x.y` versions (where `major == 0` and `minor > 0`, e.g., `^0.2.3`), the parser currently locks compatibility to the major boundary (`<1.0.0`) just like `>=1.0.0` releases. Per our SemVer specification, `0.x` minor bumps are breaking changes.
2. **Stale transitive constraints retained across solver backtracking**:
   When `DependencyResolver.resolve()` explores a candidate version of package A that introduces a constraint on package B, and later backtracks to try an older version of package A (because a sibling or deeper requirement conflicted), the constraint recorded from the abandoned version of package A is not cleanly scoped/rolled back in the active resolution state.

---

## Behavioral Specification

### 1. Version & Constraint Semantics (`r08s3pkg.semver`)
- `Version.parse("MAJOR.MINOR.PATCH")` parses non-negative integers into a total-ordered `Version(major, minor, patch)`.
- `ConstraintSpec.parse(expr)` parses comma-separated clauses (e.g. `">=1.2.0, <2.0.0"`, `"^1.2.3"`, `"~1.2.3"`, `"==1.0.0"`). A version satisfies a `ConstraintSpec` iff it satisfies **all** clauses in the spec.
- Supported single-clause operators:
  - `==X.Y.Z` (or bare `X.Y.Z`), `!=X.Y.Z`, `>=X.Y.Z`, `<=X.Y.Z`, `>X.Y.Z`, `<X.Y.Z`.
  - `~X.Y.Z` (tilde): allows patch-level changes `>=X.Y.Z` and `<X.(Y+1).0`.
  - `^X.Y.Z` (caret):
    - If `X > 0`: `>=X.Y.Z, <(X+1).0.0`
    - If `X == 0` and `Y > 0`: `>=0.Y.Z, <0.(Y+1).0`
    - If `X == 0` and `Y == 0`: `>=0.0.Z, <0.0.(Z+1)` (exact patch `0.0.Z`)

### 2. Dependency Resolution & Lockfile Planning (`r08s3pkg.resolver`)
- `PackageRegistry` stores available `Release(name, version, dependencies)` records per package, where `dependencies` maps `dep_name -> constraint_str`.
- `DependencyResolver.resolve(root_requirements: dict[str, str]) -> LockPlan`:
  - Prefers the **highest available version** first for each package in deterministic order.
  - Every chosen package version in the final `LockPlan` must satisfy **all** active constraints from `root_requirements` and from the selected versions of all packages present in the final plan.
  - If a candidate version leads to a conflict down the tree, backtracking must discard any transitive constraints and sub-selections introduced *only* by that rejected candidate version before trying the next candidate version.
  - Raises `ResolutionConflictError` if no valid assignment exists.
  - `LockPlan.install_order()` returns selected `(name, Version)` pairs in valid topological order (dependencies installed before dependents; ties broken alphabetically by package name).
