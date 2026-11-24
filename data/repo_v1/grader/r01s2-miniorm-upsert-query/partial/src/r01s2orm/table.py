from copy import deepcopy
from typing import Any
from r01s2orm.schema import ConstraintError, Schema
from r01s2orm.query import Query


class Table:
    def __init__(self, name: str, schema: Schema) -> None:
        self.name = name
        self.schema = schema
        self._rows: dict[Any, dict[str, Any]] = {}
        self._unique_indexes: dict[str, dict[Any, Any]] = {
            col: {} for col in schema.unique_columns
        }
        self._snapshots: dict[str, tuple[dict[Any, dict[str, Any]], dict[str, dict[Any, Any]]]] = {}

    def query(self) -> Query:
        return Query(self)

    def get(self, pk: Any) -> dict[str, Any] | None:
        row = self._rows.get(pk)
        return dict(row) if row is not None else None

    def all_rows(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self._rows.values()]

    def find_by_unique(self, col_name: str, value: Any) -> dict[str, Any] | None:
        if col_name not in self._unique_indexes:
            raise KeyError(f"Column '{col_name}' is not a unique indexed column")
        pk = self._unique_indexes[col_name].get(value)
        return self.get(pk) if pk is not None else None

    def upsert(self, record: dict[str, Any], on_conflict: str = "raise") -> dict[str, Any]:
        if on_conflict not in ("raise", "update", "ignore"):
            raise ValueError(f"Invalid on_conflict mode: {on_conflict}")

        clean = self.schema.normalize_record(record)
        pk = clean[self.schema.pk_name]
        existing = self._rows.get(pk)

        if existing is not None:
            if on_conflict == "raise":
                raise ConstraintError(f"Duplicate primary key: {pk}")
            if on_conflict == "ignore":
                return dict(existing)

        for col in self.schema.unique_columns:
            val = clean.get(col)
            if val is not None:
                owner_pk = self._unique_indexes[col].get(val)
                if owner_pk is not None and owner_pk != pk:
                    raise ConstraintError(f"Unique constraint violated on '{col}'={val!r}")

        if existing is not None:
            for col in self.schema.unique_columns:
                old_val = existing.get(col)
                if old_val is not None:
                    self._unique_indexes[col].pop(old_val, None)

        for col in self.schema.unique_columns:
            val = clean.get(col)
            if val is not None:
                self._unique_indexes[col][val] = pk

        self._rows[pk] = clean
        return dict(clean)

    def delete(self, pk: Any) -> bool:
        existing = self._rows.pop(pk, None)
        if existing is None:
            return False
        for col in self.schema.unique_columns:
            old_val = existing.get(col)
            if old_val is not None:
                self._unique_indexes[col].pop(old_val, None)
        return True

    def snapshot(self, tag: str) -> None:
        self._snapshots[tag] = (deepcopy(self._rows), deepcopy(self._unique_indexes))

    def rollback(self, tag: str) -> None:
        if tag not in self._snapshots:
            raise KeyError(f"Unknown snapshot tag: {tag}")
        rows_copy, idx_copy = self._snapshots[tag]
        self._rows = deepcopy(rows_copy)
        self._unique_indexes = deepcopy(idx_copy)
