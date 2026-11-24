from typing import Any, Callable


class Predicate:
    def __init__(self, field: str, op: str, target: Any) -> None:
        self.field = field
        self.op = op
        self.target = target

    @classmethod
    def from_kwarg(cls, key: str, value: Any) -> "Predicate":
        if "__" in key:
            field, op = key.rsplit("__", 1)
        else:
            field, op = key, "eq"
        if op not in {"eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"}:
            raise ValueError(f"Unsupported operator: {op}")
        return cls(field, op, value)

    def matches(self, row: dict[str, Any]) -> bool:
        val = row.get(self.field)
        if self.op == "eq":
            return val == self.target
        if self.op == "ne":
            return val != self.target
        if self.op == "in":
            return val in self.target
        if val is None:
            return False
        if self.op == "gt":
            return val > self.target
        if self.op == "gte":
            return val >= self.target
        if self.op == "lt":
            return val < self.target
        if self.op == "lte":
            return val <= self.target
        if self.op == "contains":
            return self.target in val
        return False


class Query:
    def __init__(self, rows_provider: Callable[[], list[dict[str, Any]]]) -> None:
        self._rows_provider = rows_provider
        self._predicates: list[Predicate] = []
        self._order_col: str | None = None
        self._descending: bool = False
        self._limit_val: int | None = None
        self._offset_val: int = 0

    def where(self, **filters: Any) -> "Query":
        for k, v in filters.items():
            self._predicates.append(Predicate.from_kwarg(k, v))
        return self

    def order_by(self, column: str, descending: bool = False) -> "Query":
        self._order_col = column
        self._descending = descending
        return self

    def limit(self, count: int) -> "Query":
        self._limit_val = count
        return self

    def offset(self, count: int) -> "Query":
        self._offset_val = count
        return self

    def all(self) -> list[dict[str, Any]]:
        results = [
            dict(r)
            for r in self._rows_provider()
            if all(p.matches(r) for p in self._predicates)
        ]
        if self._order_col is not None:
            col = self._order_col
            non_null = [r for r in results if r.get(col) is not None]
            nulls = [r for r in results if r.get(col) is None]
            non_null.sort(key=lambda r: r[col], reverse=self._descending)
            results = non_null + nulls
        if self._offset_val:
            results = results[self._offset_val :]
        if self._limit_val is not None:
            results = results[: self._limit_val]
        return results

    def count(self) -> int:
        return len(self.all())
