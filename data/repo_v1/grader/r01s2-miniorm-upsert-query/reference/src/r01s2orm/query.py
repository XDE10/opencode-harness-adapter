from functools import cmp_to_key
from typing import Any, Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from r01s2orm.table import Table

Predicate = Callable[[dict[str, Any]], bool]


class Query:
    def __init__(
        self,
        table: "Table",
        predicates: Optional[list[Predicate]] = None,
        joins: Optional[list[tuple["Table", str, str, str]]] = None,
        order_specs: Optional[list[tuple[str, bool]]] = None,
        offset_val: int = 0,
        limit_val: Optional[int] = None,
    ) -> None:
        self._table = table
        self._predicates: list[Predicate] = list(predicates) if predicates is not None else []
        self._joins: list[tuple["Table", str, str, str]] = list(joins) if joins is not None else []
        self._order_specs: list[tuple[str, bool]] = list(order_specs) if order_specs is not None else []
        self._offset_val = offset_val
        self._limit_val = limit_val

    def _clone(
        self,
        *,
        offset_val: Optional[int] = None,
        limit_val: Optional[int] = None,
    ) -> "Query":
        return Query(
            table=self._table,
            predicates=list(self._predicates),
            joins=list(self._joins),
            order_specs=list(self._order_specs),
            offset_val=self._offset_val if offset_val is None else offset_val,
            limit_val=self._limit_val if limit_val is None else limit_val,
        )

    def where(self, predicate: Predicate) -> "Query":
        cloned = self._clone()
        cloned._predicates.append(predicate)
        return cloned

    def join(
        self,
        other: "Table",
        left_key: str,
        right_key: str,
        prefix: str = "joined_",
    ) -> "Query":
        cloned = self._clone()
        cloned._joins.append((other, left_key, right_key, prefix))
        return cloned

    def order_by(self, field: str, descending: bool = False) -> "Query":
        cloned = self._clone()
        cloned._order_specs.append((field, descending))
        return cloned

    def offset(self, count: int) -> "Query":
        if count < 0:
            raise ValueError("offset must be non-negative")
        return self._clone(offset_val=count)

    def limit(self, count: int) -> "Query":
        if count < 0:
            raise ValueError("limit must be non-negative")
        return self._clone(limit_val=count)

    def _evaluate_matched(self) -> list[dict[str, Any]]:
        rows = self._table.all_rows()
        for other_table, left_key, right_key, prefix in self._joins:
            other_rows = other_table.all_rows()
            joined: list[dict[str, Any]] = []
            for left in rows:
                lval = left.get(left_key)
                for right in other_rows:
                    if lval is not None and lval == right.get(right_key):
                        merged = dict(left)
                        for k, v in right.items():
                            merged[f"{prefix}{k}"] = v
                        joined.append(merged)
            rows = joined

        for pred in self._predicates:
            rows = [r for r in rows if pred(r)]

        if self._order_specs:
            def compare(a: dict[str, Any], b: dict[str, Any]) -> int:
                for field, desc in self._order_specs:
                    va, vb = a.get(field), b.get(field)
                    if va == vb:
                        continue
                    res = -1 if va < vb else 1
                    return -res if desc else res
                return 0

            rows.sort(key=cmp_to_key(compare))
        return rows

    def all(self) -> list[dict[str, Any]]:
        rows = self._evaluate_matched()
        start = self._offset_val
        if self._limit_val is None:
            return rows[start:]
        return rows[start : start + self._limit_val]

    def count(self) -> int:
        return len(self._evaluate_matched())
