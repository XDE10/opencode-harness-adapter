# Issue Report: `miniorm` Schema Coercion and Query Engine Bugs

## Background
`miniorm` is a lightweight in-memory relational table and query engine used by internal batch jobs to ingest raw dictionaries, coerce them against a declared `Schema`, and run filter/sort/limit/join queries.

Two production regressions have been reported:

1. **Boolean String Coercion & Default Mutation in Schema Validation**
   - Raw records coming from CSV/env payloads often pass string representations for boolean columns (e.g., `"false"`, `"0"`, `"no"`, `"true"`, `"1"`, `"yes"`, case-insensitive with optional surrounding whitespace). Currently, string values like `"false"` or `"0"` are evaluated using Python truthiness and coerced to `True` instead of `False` (and invalid strings are not rejected with `ValueError`).
   - Additionally, when a column defines a mutable default value (such as a `list` or `dict`), mutating that field on one inserted row unexpectedly mutates the default across future inserted rows.

2. **Filtered Update Index Desynchronization & Descending Null Ordering in Query Engine**
   - `Table.update_where(changes, **filters)` updates matching rows and attempts to maintain the table's unique column indexes. However, when a non-indexed column is updated or when a unique column is updated to a new value, the unique index either fails to remove the old key or falsely raises a duplicate key `ValueError` against the row's own existing unique key.
   - `Query.order_by(column, descending=...)` is required to always place `None` values **last** (at the end of the result list), regardless of whether `descending=False` or `descending=True`. Currently, `None` values are placed first when `descending=True`.

## Behavioral Specification

### `miniorm.schema` (`Column`, `Schema`)
- Supported column types: `int`, `float`, `str`, `bool`, `list`, `dict`.
- If a field is missing from the input dictionary or its value is `None`:
  - If `default` is provided (not `None`), assign a deep copy of `default` so mutable defaults are never shared across rows.
  - Else if `nullable=True`, the value remains `None`.
  - Else raise `ValueError`.
- Type coercion rules when value is not `None`:
  - `bool`:
    - If `isinstance(val, bool)`, return `val`.
    - If `isinstance(val, int)`, `0` -> `False`, `1` -> `True` (other ints raise `ValueError`).
    - If `isinstance(val, str)`, strip whitespace and lower-case:
      - `"true"`, `"1"`, `"yes"` -> `True`
      - `"false"`, `"0"`, `"no"` -> `False`
      - Any other string -> raise `ValueError`.
    - Any other type -> raise `ValueError`.
  - `int`, `float`, `str`: coerce via `col.col_type(val)` (note: `bool` is not a valid `int` or `float` input; if `col.col_type in (int, float)` and `isinstance(val, bool)`, raise `ValueError`).
  - `list`, `dict`: must already be an instance of `list` or `dict` respectively (return a copy so external mutations do not affect validated data), otherwise raise `ValueError`.

### `miniorm.query` (`Predicate`, `Query`)
- `Query.where(**filters)` supports Django-style lookup suffixes:
  - `col=val` or `col__eq=val`
  - `col__ne=val`
  - `col__gt=val`, `col__gte=val`, `col__lt=val`, `col__lte=val` (if row value is `None`, comparison predicates return `False`)
  - `col__in=iterable`
  - `col__contains=substring_or_element`
- `Query.order_by(column, descending=False)`:
  - Non-null values are sorted in ascending (`descending=False`) or descending (`descending=True`) order.
  - Rows where `row[column] is None` must **always** appear after all non-null rows, preserving their relative order.
- `Query.limit(n)` and `Query.offset(n)` slice the ordered result set.

### `miniorm.engine` (`Table`)
- `Table.insert(record)` validates/coerces via `Schema`, checks all `unique=True` columns, stores the row, and updates unique indexes.
- `Table.update_where(changes, **filters)`:
  - Finds all rows matching `**filters`.
  - Validates the candidate updated row through `self.schema.validate(...)`.
  - Checks uniqueness constraints: a row keeps its own existing value on unchanged unique columns without conflicting with itself, while updating a unique column must not conflict with any other row in the table and must replace the old entry in the unique index.
  - Returns the number of updated rows.
