from dataclasses import dataclass, field
from typing import Any


class ConfigError(Exception):
    """Raised when configuration parsing, interpolation, inheritance, or validation fails."""


@dataclass(frozen=True)
class FieldSpec:
    type: str = "str"
    required: bool = True
    default: Any = None


@dataclass
class ConfigSchema:
    sections: dict[str, dict[str, FieldSpec]] = field(default_factory=dict)

    def add_field(
        self,
        section: str,
        key: str,
        type: str = "str",
        required: bool = True,
        default: Any = None,
    ) -> None:
        sec = self.sections.setdefault(section, {})
        sec[key] = FieldSpec(type=type, required=required, default=default)

    def coerce_value(self, section: str, key: str, raw: str, spec: FieldSpec) -> Any:
        if spec.type == "str":
            return raw
        if spec.type == "int":
            try:
                return int(raw)
            except ValueError as exc:
                raise ConfigError(f"Invalid int for {section}.{key}: {raw!r}") from exc
        if spec.type == "bool":
            lowered = raw.strip().lower()
            if lowered in ("true", "1", "yes"):
                return True
            if lowered in ("false", "0", "no"):
                return False
            raise ConfigError(f"Invalid bool for {section}.{key}: {raw!r}")
        if spec.type == "list":
            stripped = raw.strip()
            if not stripped:
                return []
            return [item.strip() for item in stripped.split(",") if item.strip()]
        raise ConfigError(f"Unsupported field type: {spec.type}")

    def validate(self, data: dict[str, dict[str, str]]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {
            sec: dict(kvs) for sec, kvs in data.items()
        }
        for section, specs in self.sections.items():
            sec_data = result.setdefault(section, {})
            for key, spec in specs.items():
                if key not in sec_data:
                    if spec.required and spec.default is None:
                        raise ConfigError(f"Missing required config key: {section}.{key}")
                    sec_data[key] = spec.default
                else:
                    sec_data[key] = self.coerce_value(
                        section, key, str(sec_data[key]), spec
                    )
        return result
