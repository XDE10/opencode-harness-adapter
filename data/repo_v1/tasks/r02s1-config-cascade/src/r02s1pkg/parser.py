import re
from typing import Mapping
from r02s1pkg.schema import ConfigError

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def strip_quotes(val: str) -> str:
    if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == "'" and val[-1] == "'")):
        return val[1:-1]
    return val


def parse_config_text(text: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current_section = "default"

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            sec_name = line[1:-1].strip()
            if not sec_name:
                raise ConfigError(f"Empty section header on line {line_no}")
            current_section = sec_name
            sections.setdefault(current_section, {})
            continue
        if "=" not in line:
            raise ConfigError(f"Malformed config line {line_no}: {raw_line!r}")
        key, raw_val = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"Empty key on line {line_no}")
        val = strip_quotes(raw_val.strip())
        sections.setdefault(current_section, {})[key] = val

    return sections


def interpolate_value(raw: str, env: Mapping[str, str]) -> str:
    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default_val = match.group(2)
        if var_name in env and env[var_name]:
            return env[var_name]
        if default_val:
            return default_val
        raise ConfigError(f"Missing required environment variable: {var_name}")

    return _ENV_PATTERN.sub(_replace, raw)
