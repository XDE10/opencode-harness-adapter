from typing import Any, Mapping
from r02s1pkg.schema import ConfigError, ConfigSchema
from r02s1pkg.parser import parse_config_text, interpolate_value


class ConfigLoader:
    def __init__(
        self,
        files: Mapping[str, str],
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._files = dict(files)
        self._env: dict[str, str] = dict(env) if env is not None else {}
        self._parsed_cache: dict[str, dict[str, dict[str, str]]] = {}

    def _get_parsed(self, filename: str) -> dict[str, dict[str, str]]:
        if filename not in self._files:
            raise ConfigError(f"Config file not found: {filename}")
        if filename not in self._parsed_cache:
            self._parsed_cache[filename] = parse_config_text(self._files[filename])
        return self._parsed_cache[filename]

    def _resolve_chain(
        self, filename: str, stack: tuple[str, ...] = ()
    ) -> dict[str, dict[str, str]]:
        if filename in stack:
            raise ConfigError("Circular config inheritance detected")
        current = self._get_parsed(filename)
        meta = current.get("meta", {})
        extends_raw = meta.get("extends", "").strip()

        merged: dict[str, dict[str, str]] = {
            sec: dict(kvs) for sec, kvs in current.items() if sec != "meta"
        }

        if extends_raw:
            parents = [p.strip() for p in extends_raw.split(",") if p.strip()]
            for parent_file in parents:
                parent_data = self._resolve_chain(parent_file, stack + (filename,))
                for sec, kvs in parent_data.items():
                    if sec == "meta":
                        continue
                    merged.setdefault(sec, {}).update(kvs)

        return merged

    def load(
        self,
        entry_file: str,
        schema: ConfigSchema | None = None,
    ) -> dict[str, dict[str, Any]]:
        raw_merged = self._resolve_chain(entry_file)
        interpolated: dict[str, dict[str, str]] = {}
        for sec, kvs in raw_merged.items():
            interpolated[sec] = {}
            for key, val in kvs.items():
                interpolated[sec][key] = interpolate_value(val, self._env)

        if schema is not None:
            return schema.validate(interpolated)
        return interpolated
