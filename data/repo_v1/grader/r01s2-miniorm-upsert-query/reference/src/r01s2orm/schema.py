from dataclasses import dataclass
from typing import Any, Callable, Optional


class ConstraintError(ValueError):
    """Raised when primary key, type, or unique constraints are violated."""


@dataclass(frozen=True)
class Column:
    name: str
    col_type: type
    primary_key: bool = False
    unique: bool = False
    nullable: bool = False
    default: Any = None
    normalizer: Optional[Callable[[Any], Any]] = None


class Schema:
    def __init__(self, columns: list[Column]) -> None:
        pk_cols = [c for c in columns if c.primary_key]
        if len(pk_cols) != 1:
            raise ValueError("Schema must define exactly one primary_key column")
        self.columns: dict[str, Column] = {c.name: c for c in columns}
        self.pk_name: str = pk_cols[0].name
        self.unique_columns: tuple[str, ...] = tuple(
            c.name for c in columns if c.unique and not c.primary_key
        )

    def normalize_record(self, raw: dict[str, Any]) -> dict[str, Any]:
        unknown = set(raw.keys()) - set(self.columns.keys())
        if unknown:
            raise ConstraintError(f"Unknown columns: {sorted(unknown)}")

        cleaned: dict[str, Any] = {}
        for name, col in self.columns.items():
            val = raw.get(name, col.default() if callable(col.default) else col.default)
            if val is None:
                if not col.nullable and not col.primary_key:
                    raise ConstraintError(f"Column '{name}' cannot be null")
                if col.primary_key:
                    raise ConstraintError(f"Primary key '{name}' cannot be null")
                cleaned[name] = None
                continue

            if col.normalizer is not None:
                val = col.normalizer(val)
            if not isinstance(val, col.col_type):
                raise ConstraintError(
                    f"Column '{name}' expected {col.col_type.__name__}, got {type(val).__name__}"
                )
            cleaned[name] = val
        return cleaned
