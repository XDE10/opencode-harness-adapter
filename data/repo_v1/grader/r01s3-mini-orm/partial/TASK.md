# Issue Report: `r01s3pkg` In-Memory Table & Query Engine

## Summary
We found two behavioral bugs in `r01s3pkg`, our lightweight in-memory ORM and query engine:
1. Default values and string-to-boolean coercion during row normalization in `Schema.validate_row`.
2. Stateful query reuse and `None`-safe sorting in `Query.execute` / `Table.query`.

## Behavioral Specification

### 1. Schema Validation & Coercion (`r01s3pkg.schema`)
- `Field(name, field_type, required=True, default=None, nullable=False)` defines a column.
  - Supported `field_type` values: `int`, `float`, `str`, `bool`.
- `Schema.validate_row(raw_row)`:
  - For each defined field:
    - If `field.name` is missing from `raw_row` or its value in `raw_row` is `None`:
      - If `field.default is not None`: use `field.default()` if `callable(field.default)` else a shallow copy (`list(val)` / `dict(val)`) or value of `field.default`.
      - Else if `field.nullable` is `True`: the value becomes `None`.
      - Else if `field.required` is `False`: the value becomes `None`.
      - Else: raise `ValueError(f"Missing required field: {field.name}")`.
    - If the resolved value is not `None`, coerce it to `field.field_type`:
      - `bool`:
        - If already a `bool`, keep as-is.
        - If a `str`, case-insensitively parse `"true"`, `"1"`, `"yes"` -> `True`, and `"false"`, `"0"`, `"no"` -> `False`. Any other string must raise `ValueError`.
        - If an `int` (`0` or `1`), coerce via `bool(val)`. Other ints raise `ValueError`.
      - `int`: if `isinstance(val, bool)`, raise `ValueError` (booleans are not valid ints). Otherwise `int(val)`.
      - `float`: if `isinstance(val, bool)`, raise `ValueError`. Otherwise `float(val)`.
      - `str`: `str(val)`.
  - Unknown fields present in `raw_row` that are not in the schema must be rejected with `ValueError`.

### 2. Predicates & Query Execution (`r01s3pkg.query`)
- `Predicate` supports operators: `"="`, `"!="`, `"<"`, `"<="`, `">"`, `">="`, `"in"`, `"contains"`.
  - When a field's value in a row is `None`:
    - `"="` evaluates to `True` only if `predicate.value is None`.
    - `"!="` evaluates to `True` only if `predicate.value is not None`.
    - Comparison operators (`"<"`, `"<="`, `">"`, `">="`), `"in"`, and `"contains"` must return `False` (never raise `TypeError`) when the row's field value is `None`.
- `Query` methods (`where`, `order_by`, `limit`, `offset`, `join`) return a new or updated query builder, and `execute()`:
  - Must not mutate stored table rows in place when `join()` or projection is executed; subsequent queries on the original `Table` must see unmodified rows.
  - When `order_by(field, descending=False)` is applied on a column that contains `None` values:
    - Non-`None` values are sorted in ascending order (if `descending=False`) or descending order (if `descending=True`).
    - `None` values must **always be placed last** regardless of whether `descending` is `False` or `True`.
  - `offset` is applied after sorting, and `limit` is applied after `offset`.
