import copy
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Column:
    name: str
    col_type: type
    nullable: bool = False
    unique: bool = False
    default: Any = None


class Schema:
    def __init__(self, columns: list[Column]) -> None:
        self.columns: dict[str, Column] = {c.name: c for c in columns}
        self.unique_columns: list[str] = [c.name for c in columns if c.unique]

    def coerce_value(self, col: Column, val: Any) -> Any:
        if val is None:
            if col.default is not None:
                return copy.deepcopy(col.default)
            if col.nullable:
                return None
            raise ValueError(f"Column '{col.name}' cannot be null")

        if col.col_type is bool:
            if isinstance(val, bool):
                return val
            if isinstance(val, int):
                if val in (0, 1):
                    return bool(val)
                raise ValueError(f"Invalid boolean int for '{col.name}': {val!r}")
            if isinstance(val, str):
                norm = val.strip().lower()
                if norm in ("true", "1", "yes"):
                    return True
                if norm in ("false", "0", "no"):
                    return False
                raise ValueError(f"Invalid boolean string for '{col.name}': {val!r}")
            raise ValueError(f"Invalid boolean value for '{col.name}': {val!r}")

        if col.col_type is int:
            if isinstance(val, bool):
                raise ValueError(f"Invalid int for '{col.name}': {val!r}")
            return int(val)

        if col.col_type is float:
            if isinstance(val, bool):
                raise ValueError(f"Invalid float for '{col.name}': {val!r}")
            return float(val)

        if col.col_type is str:
            return str(val)

        if col.col_type in (list, dict):
            if not isinstance(val, col.col_type):
                raise ValueError(f"Expected {col.col_type.__name__} for '{col.name}'")
            return copy.deepcopy(val)

        raise TypeError(f"Unsupported column type: {col.col_type}")

    def validate(self, record: dict[str, Any]) -> dict[str, Any]:
        unknown = set(record.keys()) - set(self.columns.keys())
        if unknown:
            raise ValueError(f"Unknown columns: {sorted(unknown)}")
        validated: dict[str, Any] = {}
        for name, col in self.columns.items():
            raw_val = record.get(name, None)
            validated[name] = self.coerce_value(col, raw_val)
        return validated
