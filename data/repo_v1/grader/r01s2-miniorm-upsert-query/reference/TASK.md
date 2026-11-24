# Issue Report: `r01s2orm` Upsert Conflict Rollback & Chained Query Pagination

## Context
`r01s2orm` is a lightweight in-memory table and query composition engine used for local caching and transactional staging. It consists of:
- `schema.py`: `Column`, `Schema`, and `ConstraintError` for validating and normalizing records, plus unique secondary index extraction.
- `table.py`: `Table` managing primary key storage, secondary unique constraint indexes, transactional `upsert()`, and savepoint `snapshot()` / `rollback()`.
- `query.py`: `Query` providing immutable multi-step query composition (`where`, `join`, `order_by`, `offset`, `limit`) and execution (`all`, `count`).

## Reported Symptoms
1. **Unique constraint failures during `upsert(..., on_conflict="update")` corrupt unique index state**:
   When a row with an existing primary key is updated via `upsert(record, on_conflict="update")`, if the updated values violate a secondary `unique=True` column constraint held by *another* row, `ConstraintError` is raised as expected. However, after catching `ConstraintError`, querying or inserting with the original row's old unique column value behaves as if the old unique index entry was already evicted or overwritten. If an upsert fails validation or unique constraint checks, the table and all unique indexes must remain completely unchanged. Furthermore, updating an existing row's non-unique fields (keeping its own unique column value unchanged) must not falsely conflict with itself.
2. **Chained `Query` composition mutates prior query instances and miscalculates `offset` + `limit` windowing**:
   - Calling `.where()`, `.order_by()`, `.offset()`, or `.limit()` on a base `Query` object unexpectedly leaks filter predicates or sort keys into previously branched `Query` objects. Every builder method on `Query` must return a fresh independent `Query` without mutating the receiver.
   - When both `.offset(k)` and `.limit(n)` are applied to a query, `.all()` returns the wrong slice (currently treating the second slice parameter as an absolute end index `n` instead of taking up to `n` rows after skipping `k` rows). Also, `.count()` on a query should return the total number of rows matching the `where`/`join` predicates *before* `offset` and `limit` slicing are applied.

## Behavioral Specification
- `Table.upsert(record, on_conflict="raise" | "update" | "ignore")`:
  - Validates and normalizes `record` against `Schema`.
  - If the primary key does not exist: checks secondary unique constraints; if any unique column value is already owned by another PK, raises `ConstraintError` without modifying storage or indexes. Otherwise inserts the row and updates all unique indexes.
  - If the primary key already exists:
    - `on_conflict="raise"`: raises `ConstraintError` with no state changes.
    - `on_conflict="ignore"`: returns the existing stored row copy without modifying state.
    - `on_conflict="update"`: checks if any unique column in the normalized record conflicts with a *different* primary key. If a conflict exists, raises `ConstraintError` and leaves the existing row and all unique indexes intact. If valid, removes stale unique index entries for the old row, stores the updated row, and registers the new unique index entries.
- `Query` immutability and execution:
  - `Query.where(predicate)`, `Query.join(...)`, `Query.order_by(field, descending=False)`, `Query.offset(count)`, and `Query.limit(count)` must each return a new `Query` instance leaving the original `Query` unmodified.
  - Multiple `order_by` calls sort by the specified fields in priority order (first added = primary sort key, later added = tie-breaker).
  - `Query.all()` applies filters, optional join, ordering, skips `offset` rows, and returns at most `limit` rows (if `limit` is not `None`).
  - `Query.count()` returns the number of matched (and joined, if applicable) records prior to `offset` and `limit`.
