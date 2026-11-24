from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Field:
    name: str
    field_type: type
    required: bool = True
    default: Any = None
    nullable: bool = False


class Schema:
    def __init__(self, fields: list[Field]) -> None:
        self.fields: dict[str, Field] = {f.name: f for f in fields}

    def validate_row(self, raw_row: dict[str, Any]) -> dict[str, Any]:
        unknown = set(raw_row.keys()) - set(self.fields.keys())
        if unknown:
            raise ValueError(f"Unknown fields: {sorted(unknown)}")

        cleaned: dict[str, Any] = {}
        for name, field in self.fields.items():
            val = raw_row.get(name, None)
            if val is None:
                if field.default is not None:
                    val = field.default() if callable(field.default) else field.default
                elif field.nullable or not field.required:
                    cleaned[name] = None
                    continue
                else:
                    raise ValueError(f"Missing required field: {name}")

            cleaned[name] = self._coerce(field, val)
        return cleaned

    def _coerce(self, field: Field, val: Any) -> Any:
        target = field.field_type
        if target is bool:
            if isinstance(val, bool):
                return val
            if isinstance(val, str):
                norm = val.strip().lower()
                if norm in ("true", "1", "yes"):
                    return True
                if norm in ("false", "0", "no"):
                    return False
                raise ValueError(f"Invalid boolean string for {field.name}: {val!r}")
            if isinstance(val, int) and val in (0, 1):
                return bool(val)
            raise ValueError(f"Cannot coerce {val!r} to bool for {field.name}")
        if target is int:
            if isinstance(val, bool):
                raise ValueError(f"Cannot coerce bool to int for {field.name}")
            return int(val)
        if target is float:
            if isinstance(val, bool):
                raise ValueError(f"Cannot coerce bool to float for {field.name}")
            return float(val)
        if target is str:
            return str(val)
        raise ValueError(f"Unsupported field type: {target}")
