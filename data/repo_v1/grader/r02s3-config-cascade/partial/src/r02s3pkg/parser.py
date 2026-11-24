from dataclasses import dataclass
import re
from typing import Any

ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ConfigError(Exception):
    """Raised when configuration parsing, inheritance, or validation fails."""


@dataclass(frozen=True)
class RawValue:
    text: str
    quoted: bool = False


def _strip_inline_comment(line: str) -> str:
    in_quotes = False
    for idx, ch in enumerate(line):
        if ch == '"' and (idx == 0 or line[idx - 1] != "\\"):
            in_quotes = not in_quotes
        elif ch == "#" and not in_quotes:
            return line[:idx].strip()
    return line.strip()


def coerce_scalar(text: str, quoted: bool = False) -> Any:
    if quoted:
        return text
    low = text.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "none"):
        return None
    if "," in text:
        return [coerce_scalar(part.strip(), False) for part in text.split(",") if part.strip()]
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def interpolate_value(raw: RawValue, env: dict[str, str]) -> Any:
    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default_val = match.group(2)
        val = env.get(var_name)
        if val is not None and val != "":
            return val
        if default_val is not None:
            return default_val
        if var_name in env and val == "":
            return ""
        raise ConfigError(f"Missing required environment variable: {var_name}")

    expanded = ENV_PATTERN.sub(_replace, raw.text)
    if raw.quoted:
        return expanded
    return coerce_scalar(expanded, quoted=False)


def parse_config_text(content: str) -> dict[str, dict[str, RawValue]]:
    sections: dict[str, dict[str, RawValue]] = {}
    current_section: str | None = None

    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        cleaned = _strip_inline_comment(raw_line)
        if not cleaned:
            continue
        if cleaned.startswith("[") and cleaned.endswith("]"):
            sec_name = cleaned[1:-1].strip()
            if not sec_name:
                raise ConfigError(f"Empty section header at line {line_no}")
            current_section = sec_name
            sections.setdefault(current_section, {})
            continue
        if current_section is None:
            raise ConfigError(f"Key-value pair outside section at line {line_no}")
        if "=" not in cleaned:
            raise ConfigError(f"Malformed line {line_no}: {raw_line}")
        key, val = cleaned.split("=", 1)
        key = key.strip()
        val = val.strip()
        if not key:
            raise ConfigError(f"Empty key at line {line_no}")
        if len(val) >= 2 and val.startswith('"') and val.endswith('"'):
            sections[current_section][key] = RawValue(val[1:-1], quoted=True)
        else:
            sections[current_section][key] = RawValue(val, quoted=False)

    return sections
