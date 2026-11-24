from typing import Any
from r02s3pkg.parser import ConfigError, RawValue, parse_config_text, interpolate_value
from r02s3pkg.schema import ConfigSchema


class ConfigCascade:
    def __init__(self, schema: ConfigSchema | None = None) -> None:
        self.schema = schema
        self._layers: list[dict[str, dict[str, RawValue]]] = []

    def add_layer(self, content: str) -> None:
        parsed = parse_config_text(content)
        self._layers.append(parsed)

    def resolve(self, env: dict[str, str] | None = None) -> dict[str, dict[str, Any]]:
        env_map = dict(env or {})
        merged_raw: dict[str, dict[str, RawValue]] = {}

        for layer in self._layers:
            for section, kv in layer.items():
                sec_bucket = merged_raw.setdefault(section, {})
                for key, raw_val in kv.items():
                    sec_bucket[key] = raw_val

        interpolated: dict[str, dict[str, Any]] = {}
        for section, kv in merged_raw.items():
            interpolated[section] = {
                key: interpolate_value(raw_val, env_map) for key, raw_val in kv.items()
            }

        resolved = self._resolve_inheritance(interpolated)
        if self.schema is not None:
            resolved = self.schema.validate(resolved)
        return resolved

    def _resolve_inheritance(
        self, sections: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        output: dict[str, dict[str, Any]] = {}

        def _build(sec_name: str, stack: list[str]) -> dict[str, Any]:
            if sec_name in stack:
                cycle = " -> ".join(stack + [sec_name])
                raise ConfigError(f"Circular section inheritance: {cycle}")
            if sec_name not in sections:
                raise ConfigError(f"Unknown parent section '{sec_name}'")
            if sec_name in output:
                return output[sec_name]

            current = sections[sec_name]
            parent_name = current.get("extends")
            if parent_name is not None:
                parent_data = _build(str(parent_name), stack + [sec_name])
                parent_data.update(current)
                output[sec_name] = parent_data
            else:
                output[sec_name] = current
            return output[sec_name]

        for name in sections:
            _build(name, [])

        return output
