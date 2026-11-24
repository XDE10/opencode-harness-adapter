import re
from typing import Dict, List, Any, Optional
from r02s2pkg.parser import ParsedLayer, ConfigOp

TOKEN_RE = re.compile(r"\$\{([^}]+)\}")


class ConfigValidationError(Exception):
    pass


def apply_op(target: Dict[str, Any], op: ConfigOp) -> None:
    if op.op == "=":
        raw = op.raw_value.strip()
        if raw.startswith("[") and raw.endswith("]"):
            target[op.key] = op.parsed_items()
        else:
            target[op.key] = raw
    elif op.op == "+=":
        existing = target.get(op.key, [])
        for item in op.parsed_items():
            existing.append(item)
        target[op.key] = existing
    elif op.op == "-=":
        existing = target.get(op.key, [])
        for item in op.parsed_items():
            if item in existing:
                existing.remove(item)
        target[op.key] = existing


def compile_layers(layers: List[ParsedLayer], env: Optional[Dict[str, str]] = None) -> Dict[str, Dict[str, Any]]:
    env_map = env or {}
    raw_sections: Dict[str, Dict[str, Any]] = {}
    parents: Dict[str, Optional[str]] = {}

    for layer in layers:
        for sec_name, sec in layer.sections.items():
            if sec.parent is not None:
                parents[sec_name] = sec.parent
            elif sec_name not in parents:
                parents[sec_name] = None

    def resolve_section_raw(sec_name: str, visiting: set) -> Dict[str, Any]:
        if sec_name in raw_sections:
            return raw_sections[sec_name]
        if sec_name in visiting:
            raise ValueError(f"Circular inheritance detected for section {sec_name}")
        visiting.add(sec_name)

        parent_name = parents.get(sec_name)
        if parent_name:
            base = dict(resolve_section_raw(parent_name, visiting))
        else:
            base = {}

        for layer in layers:
            if sec_name in layer.sections:
                for op in layer.sections[sec_name].ops:
                    apply_op(base, op)

        visiting.remove(sec_name)
        raw_sections[sec_name] = base
        return base

    for sec_name in list(parents.keys()):
        resolve_section_raw(sec_name, set())

    return _interpolate_all(raw_sections, env_map)


def _interpolate_all(raw_sections: Dict[str, Dict[str, Any]], env: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    def resolve_str(val: str, depth: int = 0) -> str:
        if depth > 10:
            raise ValueError("Max interpolation depth exceeded")

        def repl(match: re.Match) -> str:
            expr = match.group(1)
            if expr.startswith("ENV:"):
                rest = expr[4:]
                if ":-" in rest:
                    var_name, default = rest.split(":-", 1)
                    return env.get(var_name, default)
                return env.get(rest, "")
            if "." in expr:
                sec, key = expr.rsplit(".", 1)
                target_val = raw_sections.get(sec, {}).get(key, "")
                if isinstance(target_val, list):
                    return ",".join(resolve_str(str(x), depth + 1) for x in target_val)
                return resolve_str(str(target_val), depth + 1)
            return ""

        out = TOKEN_RE.sub(repl, val)
        if TOKEN_RE.search(out):
            return resolve_str(out, depth + 1)
        return out

    result: Dict[str, Dict[str, Any]] = {}
    for sec_name, sec_data in raw_sections.items():
        result[sec_name] = {}
        for k, v in sec_data.items():
            if isinstance(v, list):
                result[sec_name][k] = [resolve_str(str(item)) for item in v]
            else:
                result[sec_name][k] = resolve_str(str(v))
    return result


def validate_config(compiled: Dict[str, Dict[str, Any]], schema: Dict[str, Dict[str, Any]]) -> None:
    for sec_name, rules in schema.items():
        if sec_name not in compiled:
            if rules.get("required", False):
                raise ConfigValidationError(f"Missing required section: {sec_name}")
            continue
        sec_data = compiled[sec_name]
        for key, key_rule in rules.get("keys", {}).items():
            if key_rule.get("required", False) and key not in sec_data:
                raise ConfigValidationError(f"Missing required key '{key}' in section '{sec_name}'")
            if key in sec_data and "validator" in key_rule:
                if not key_rule["validator"](sec_data[key]):
                    raise ConfigValidationError(f"Validation failed for '{sec_name}.{key}'")
