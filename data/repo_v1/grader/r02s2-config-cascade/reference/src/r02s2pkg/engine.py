import copy
from fnmatch import fnmatchcase
from typing import Dict, List, Any, Optional, Callable
from r02s2pkg.parser import ParsedLayer, parse_config_text
from r02s2pkg.resolver import compile_layers, validate_config


class ConfigStore:
    def __init__(self, env: Optional[Dict[str, str]] = None) -> None:
        self.env: Dict[str, str] = dict(env or {})
        self._layers: List[ParsedLayer] = []
        self._compiled_cache: Optional[Dict[str, Dict[str, Any]]] = None

    def apply_layer(
        self,
        name: str,
        text: str,
        schema: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        parsed = parse_config_text(name, text)
        candidate_layers = list(self._layers)
        replaced = False
        for i, existing in enumerate(candidate_layers):
            if existing.name == name:
                candidate_layers[i] = parsed
                replaced = True
                break
        if not replaced:
            candidate_layers.append(parsed)

        compiled = compile_layers(candidate_layers, self.env)
        if schema is not None:
            validate_config(compiled, schema)

        self._layers = candidate_layers
        self._compiled_cache = compiled
        return copy.deepcopy(compiled)

    def rollback_layer(self, name: str) -> bool:
        for i, layer in enumerate(self._layers):
            if layer.name == name:
                self._layers.pop(i)
                self._compiled_cache = None
                return True
        return False

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        if self._compiled_cache is None:
            self._compiled_cache = compile_layers(self._layers, self.env)
        return copy.deepcopy(self._compiled_cache)

    def query(
        self,
        section_pattern: str = "*",
        key_prefix: Optional[str] = None,
        where: Optional[Callable[[Dict[str, Any]], bool]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        current = self.snapshot()
        matched: Dict[str, Dict[str, Any]] = {}
        for sec_name in sorted(current.keys()):
            if not fnmatchcase(sec_name, section_pattern):
                continue
            sec_data = current[sec_name]
            if where is not None and not where(sec_data):
                continue
            if key_prefix is not None:
                filtered = {k: v for k, v in sec_data.items() if k.startswith(key_prefix)}
            else:
                filtered = dict(sec_data)
            matched[sec_name] = filtered
        return matched
