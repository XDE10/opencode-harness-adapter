from dataclasses import dataclass
from typing import Any
from r02s3pkg.parser import ConfigError


@dataclass
class FieldSpec:
    field_type: type
    required: bool = True
    default: Any = None


class ConfigSchema:
    def __init__(self) -> None:
        self._sections: dict[str, dict[str, FieldSpec]] = {}

    def add_field(self, section: str, key: str, spec: FieldSpec) -> None:
        self._sections.setdefault(section, {})[key] = spec

    def validate(self, resolved: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        for section, specs in self._sections.items():
            if section not in resolved:
                continue
            sec_data = resolved[section]
            for key, spec in specs.items():
                val = sec_data.get(key)
                if not val:
                    if spec.default is not None:
                        sec_data[key] = spec.default
                        val = spec.default
                    elif spec.required:
                        raise ConfigError(f"Missing required field '{section}.{key}'")
                    else:
                        sec_data[key] = None
                        continue
                if val is not None and not isinstance(val, spec.field_type):
                    if spec.field_type is float and isinstance(val, int) and not isinstance(val, bool):
                        sec_data[key] = float(val)
                    else:
                        raise ConfigError(
                            f"Type mismatch for '{section}.{key}': expected {spec.field_type.__name__}, "
                            f"got {type(val).__name__}"
                        )
        return resolved
