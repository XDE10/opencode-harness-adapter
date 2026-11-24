import copy
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
            sec_data = resolved.setdefault(section, {})
            for key, spec in specs.items():
                if key not in sec_data or sec_data[key] is None:
                    if spec.default is not None:
                        sec_data[key] = copy.deepcopy(spec.default)
                    elif spec.required:
                        raise ConfigError(f"Missing required field '{section}.{key}'")
                    else:
                        sec_data[key] = None
                        continue
                val = sec_data[key]
                if val is not None and not isinstance(val, spec.field_type):
                    if (
                        spec.field_type is float
                        and isinstance(val, int)
                        and not isinstance(val, bool)
                    ):
                        sec_data[key] = float(val)
                    elif spec.field_type is int and isinstance(val, bool):
                        raise ConfigError(
                            f"Type mismatch for '{section}.{key}': expected int, got bool"
                        )
                    else:
                        raise ConfigError(
                            f"Type mismatch for '{section}.{key}': expected {spec.field_type.__name__}, "
                            f"got {type(val).__name__}"
                        )
                elif spec.field_type is int and isinstance(val, bool):
                    raise ConfigError(
                        f"Type mismatch for '{section}.{key}': expected int, got bool"
                    )
        return resolved
