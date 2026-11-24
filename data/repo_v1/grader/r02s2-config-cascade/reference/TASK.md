# Issue Report: ConfigCascade Conflict Resolution, List Operator Rollback, and Multi-Step Querying

## Context
`r02s2pkg` implements an in-memory layered YAML-lite/INI configuration store (`ConfigStore`) supporting section inheritance (`[child : parent]`), list mutation operators (`+=`, `-=`), transactional overlay commits with rollback, and environment/cross-section interpolation (`${ENV:VAR:-default}`, `${section.key}`).

## Reported Symptoms
1. **List operator conflict resolution & inheritance mutation leakage**:
   - When parsing sections in `parse_config_text`, list append (`key += val1, val2`) and list removal (`key -= val2`) entries are parsed as `ConfigOp` records.
   - When a child section inherits from a parent section (`[prod.db : base.db]`) or when multiple config layers are merged, applying `+=` or `-=` operations in the child or upper layer mutates the parent/lower layer's underlying `list` in-place instead of operating on a copy, and `-=` fails to remove all occurrences of the specified items while preserving order.
   - Furthermore, if a scalar key in a lower layer/parent section is overridden by a `+=` or `-=` operator in an upper layer/child section, conflict resolution should promote the existing scalar to a single-item list (or start from an empty list if missing/empty) before applying the list operation; currently it raises an `AttributeError`/`TypeError` or corrupts the parent entry.

2. **Transactional `apply_layer` rollback & derived query cache invalidation**:
   - `ConfigStore.apply_layer(name, text, schema=None)` parses `text`, merges it into the active layer stack, and validates the resulting interpolated view against `schema` (if provided).
   - When validation fails (raising `ConfigValidationError`), or when `rollback_layer(name)` is called to pop/remove an applied layer, the store fails to cleanly restore previous state and invalidate its cached compiled snapshot (`_compiled_cache`). As a result, subsequent `query(...)` calls still see stale values from the failed or rolled-back layer, or see mutated state from the failed attempt.

## Behavioral Specification
- **Parsing & Operators (`parser.py`)**:
  - Sections are declared as `[section]` or `[section : parent_section]`.
  - Key lines support `=`, `+=`, and `-=`:
    - `key = value`: Sets scalar string `value` (or if `value` starts with `[` and ends with `]`, parses a comma-separated list of stripped non-empty strings, e.g. `[a, b]` -> `["a", "b"]`, `[]` -> `[]`).
    - `key += a, b`: Appends stripped non-empty comma-separated items `["a", "b"]` to the target list. If the inherited/prior value was a scalar string `s`, treat it as `[s]` (if non-empty) or `[]` (if `""`) before appending. Avoid adding duplicate items that are already present in the list (set-like ordered append).
    - `key -= a, b`: Removes all occurrences of `"a"` and `"b"` from the target list while preserving relative order of remaining items (if prior value was a scalar `s`, promote to `[s]` first; if key did not exist, result is `[]`).
- **Inheritance & Layer Resolution (`resolver.py`)**:
  - Across layers (in order of application) and within each layer's `[child : parent]` inheritance chain:
    - Base values are resolved from the parent section first (recursively across the compiled state up to and including the current layer), then child/layer operations are applied on a deep copy so parent sections and earlier layers are never mutated.
  - Interpolation (`${ENV:VAR:-default}` from `env` dict, and `${section.key}` from resolved sections, where `section` may contain dots and `key` is the final dot-separated segment `rsplit(".", 1)`):
    - For any string value (or string item in a list), replace `${ENV:NAME:-fallback}` (or `${ENV:NAME}` defaulting to `""`) using `env`, and `${sec.k}` using the resolved value of `sec.k` (if `sec.k` is a list, join its resolved items with `","`).
- **Transactions, Validation & Multi-Step Query (`engine.py`)**:
  - `apply_layer(name, text, schema=None)`: If `name` already exists in the layer stack, replace it in-place at its current position; otherwise append it. If `schema` validation fails (`ConfigValidationError`), the store MUST revert to the exact state prior to `apply_layer` and re-raise `ConfigValidationError`.
  - `rollback_layer(name)`: Removes the named layer from the store, invalidates any cached snapshot, and returns `True` (or `False` if `name` was not present).
  - `query(section_pattern, key_prefix=None, where=None)`: Evaluates against the fresh compiled & interpolated configuration. Matches sections using `fnmatchcase(section, section_pattern)`, filters keys by `key_prefix` (if given), and filters the section dict by predicate `where(section_dict)` (if given). Returns a new dict `{section: {k: v}}` sorted by section name.
