from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class ConfigOp:
    key: str
    op: str  # "=", "+=", "-="
    raw_value: str

    def parsed_items(self) -> List[str]:
        val = self.raw_value.strip()
        if val.startswith("[") and val.endswith("]"):
            val = val[1:-1].strip()
        if not val:
            return []
        return [item.strip() for item in val.split(",") if item.strip()]


@dataclass
class ParsedSection:
    name: str
    parent: Optional[str] = None
    ops: List[ConfigOp] = field(default_factory=list)


@dataclass
class ParsedLayer:
    name: str
    sections: Dict[str, ParsedSection] = field(default_factory=dict)


def parse_config_text(layer_name: str, text: str) -> ParsedLayer:
    layer = ParsedLayer(name=layer_name)
    current_sec: Optional[ParsedSection] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("[") and line.endswith("]"):
            header = line[1:-1].strip()
            if ":" in header:
                sec_name, parent_name = [p.strip() for p in header.split(":", 1)]
            else:
                sec_name, parent_name = header, None
            if sec_name not in layer.sections:
                layer.sections[sec_name] = ParsedSection(name=sec_name, parent=parent_name)
            elif parent_name is not None:
                layer.sections[sec_name].parent = parent_name
            current_sec = layer.sections[sec_name]
            continue

        if current_sec is None:
            raise ValueError(f"Key assignment outside of section: {line}")

        for operator in ("+=", "-=", "="):
            if operator in line:
                k, v = line.split(operator, 1)
                current_sec.ops.append(ConfigOp(key=k.strip(), op=operator, raw_value=v.strip()))
                break
        else:
            raise ValueError(f"Invalid config line: {line}")

    return layer
