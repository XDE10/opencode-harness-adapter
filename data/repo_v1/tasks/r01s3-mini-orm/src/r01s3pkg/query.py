from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Predicate:
    field: str
    op: str
    value: Any

    def matches(self, row: dict[str, Any]) -> bool:
        actual = row.get(self.field)
        if self.op == "=":
            return actual == self.value
        if self.op == "!=":
            return actual != self.value
        if actual is None:
            return False
        if self.op == "<":
            return actual < self.value
        if self.op == "<=":
            return actual <= self.value
        if self.op == ">":
            return actual > self.value
        if self.op == ">=":
            return actual >= self.value
        if self.op == "in":
            return actual in self.value
        if self.op == "contains":
            return self.value in actual
        raise ValueError(f"Unsupported operator: {self.op}")


class Query:
    def __init__(self, source_rows: list[dict[str, Any]]) -> None:
        self._source_rows = source_rows
        self._predicates: list[Predicate] = []
        self._order_field: str | None = None
        self._descending: bool = False
        self._limit: int | None = None
        self._offset: int = 0
        self._join_spec: tuple[list[dict[str, Any]], str, str, str] | None = None

    def where(self, field: str, op: str, value: Any) -> "Query":
        self._predicates.append(Predicate(field, op, value))
        return self

    def order_by(self, field: str, descending: bool = False) -> "Query":
        self._order_field = field
        self._descending = descending
        return self

    def limit(self, count: int) -> "Query":
        self._limit = count
        return self

    def offset(self, count: int) -> "Query":
        self._offset = count
        return self

    def join(
        self,
        other_rows: list[dict[str, Any]],
        left_key: str,
        right_key: str,
        prefix: str = "joined_",
    ) -> "Query":
        self._join_spec = (other_rows, left_key, right_key, prefix)
        return self

    def execute(self) -> list[dict[str, Any]]:
        rows = list(self._source_rows)

        if self._join_spec is not None:
            other_rows, left_key, right_key, prefix = self._join_spec
            joined: list[dict[str, Any]] = []
            for left in rows:
                for right in other_rows:
                    if left.get(left_key) == right.get(right_key):
                        merged = left
                        for k, v in right.items():
                            merged[f"{prefix}{k}"] = v
                        joined.append(merged)
            rows = joined

        for pred in self._predicates:
            rows = [r for r in rows if pred.matches(r)]

        if self._order_field is not None:
            key_field = self._order_field
            rows.sort(
                key=lambda r: (r.get(key_field) is None, r.get(key_field)),
                reverse=self._descending,
            )

        if self._offset:
            rows = rows[self._offset :]
        if self._limit is not None:
            rows = rows[: self._limit]

        return [dict(r) for r in rows]
