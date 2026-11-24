from typing import Any
from r01s3pkg.schema import Schema
from r01s3pkg.query import Query


class Table:
    def __init__(self, name: str, schema: Schema) -> None:
        self.name = name
        self.schema = schema
        self._rows: list[dict[str, Any]] = []

    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        validated = self.schema.validate_row(row)
        self._rows.append(validated)
        return dict(validated)

    def insert_many(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.insert(r) for r in rows]

    def query(self) -> Query:
        return Query(self._rows)

    def count(self) -> int:
        return len(self._rows)
