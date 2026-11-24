from typing import Any
from miniorm.schema import Schema
from miniorm.query import Predicate, Query


class Table:
    def __init__(self, name: str, schema: Schema) -> None:
        self.name = name
        self.schema = schema
        self._rows: list[dict[str, Any]] = []
        self._unique_indexes: dict[str, dict[Any, int]] = {
            col: {} for col in schema.unique_columns
        }

    def insert(self, record: dict[str, Any]) -> dict[str, Any]:
        row = self.schema.validate(record)
        for col in self.schema.unique_columns:
            val = row[col]
            if val is not None and val in self._unique_indexes[col]:
                raise ValueError(f"Duplicate value {val!r} for unique column '{col}'")

        row_idx = len(self._rows)
        self._rows.append(row)
        for col in self.schema.unique_columns:
            val = row[col]
            if val is not None:
                self._unique_indexes[col][val] = row_idx
        return dict(row)

    def query(self) -> Query:
        return Query(lambda: self._rows)

    def update_where(self, changes: dict[str, Any], **filters: Any) -> int:
        predicates = [Predicate.from_kwarg(k, v) for k, v in filters.items()]
        updated_count = 0

        for idx, row in enumerate(self._rows):
            if not all(p.matches(row) for p in predicates):
                continue

            candidate = dict(row)
            candidate.update(changes)
            validated = self.schema.validate(candidate)

            for col in self.schema.unique_columns:
                new_val = validated[col]
                existing_idx = self._unique_indexes[col].get(new_val)
                if new_val is not None and existing_idx is not None and existing_idx != idx:
                    raise ValueError(f"Duplicate value {new_val!r} for unique column '{col}'")

            for col in self.schema.unique_columns:
                old_val = row[col]
                new_val = validated[col]
                if old_val is not None and old_val in self._unique_indexes[col]:
                    del self._unique_indexes[col][old_val]
                if new_val is not None:
                    self._unique_indexes[col][new_val] = idx

            self._rows[idx] = validated
            updated_count += 1

        return updated_count

    def inner_join(
        self, other: "Table", left_on: str, right_on: str, prefix: str = "right_"
    ) -> list[dict[str, Any]]:
        joined: list[dict[str, Any]] = []
        for l_row in self._rows:
            l_val = l_row.get(left_on)
            if l_val is None:
                continue
            for r_row in other._rows:
                if r_row.get(right_on) == l_val:
                    merged = dict(l_row)
                    for k, v in r_row.items():
                        out_key = k if k not in merged else f"{prefix}{k}"
                        merged[out_key] = v
                    joined.append(merged)
        return joined
