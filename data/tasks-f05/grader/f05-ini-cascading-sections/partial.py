import re

SECTION_RE = re.compile(r"^\[(.*)\]$")


def _split_kv(line):
    eq_idx = line.find("=")
    col_idx = line.find(":")
    candidates = [i for i in (eq_idx, col_idx) if i != -1]
    if not candidates:
        raise ValueError(f"missing delimiter: {line}")
    idx = min(candidates)
    key = line[:idx].strip()
    if not key:
        raise ValueError("empty key")
    return key, line[idx + 1 :].strip()


def _parse_ini(text):
    sections = {}
    parents = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in ("#", ";"):
            continue
        m = SECTION_RE.match(line)
        if m:
            header = m.group(1).strip()
            if "<" in header:
                child, parent = (part.strip() for part in header.split("<", 1))
                if not child or not parent:
                    raise ValueError("invalid inheritance header")
                if child in parents and parents[child] != parent:
                    raise ValueError(f"conflicting parent for {child}")
                parents[child] = parent
                current = child
            else:
                if not header:
                    raise ValueError("empty section name")
                current = header
            sections.setdefault(current, {})
            continue
        if current is None:
            raise ValueError("key-value outside section")
        k, v = _split_kv(line)
        sections[current][k] = v
    return sections, parents


def _collect_section(name, sections, parents, defaults, visiting):
    if name not in sections:
        raise KeyError(name)
    if name in visiting:
        raise ValueError(f"inheritance cycle at {name}")
    merged = dict(defaults or {})
    if name in parents:
        visiting.add(name)
        merged.update(_collect_section(parents[name], sections, parents, defaults, visiting))
        visiting.remove(name)
    merged.update(sections.get("DEFAULT", {}))
    merged.update(sections[name])
    return merged


def _resolve_value(sec, key, raw_sections, cache, stack):
    if (sec, key) in cache:
        return cache[(sec, key)]
    if (sec, key) in stack:
        raise ValueError(f"interpolation cycle at {sec}.{key}")
    sec_map = raw_sections[sec]
    if key not in sec_map:
        raise KeyError(f"{sec}.{key}")
    stack.add((sec, key))
    text = sec_map[key]
    out = []
    i = 0
    while i < len(text):
        if text.startswith("$$", i):
            out.append("$")
            i += 2
        elif text.startswith("${", i):
            end = text.find("}", i + 2)
            if end == -1:
                raise ValueError("unclosed placeholder")
            ref = text[i + 2 : end]
            if "." in ref:
                ref_sec, ref_key = ref.split(".", 1)
                if ref_sec not in raw_sections:
                    raise KeyError(ref_sec)
                out.append(_resolve_value(ref_sec, ref_key, raw_sections, cache, stack))
            else:
                out.append(_resolve_value(sec, ref, raw_sections, cache, stack))
            i = end + 1
        else:
            out.append(text[i])
            i += 1
    stack.remove((sec, key))
    cache[(sec, key)] = "".join(out)
    return cache[(sec, key)]


def load_ini_config(text, target_section, defaults=None):
    sections, parents = _parse_ini(text)
    if target_section not in sections:
        raise KeyError(target_section)
    raw_sections = {name: dict(sections[name]) for name in sections}
    raw_sections[target_section] = _collect_section(target_section, sections, parents, defaults, set())
    cache = {}
    return {k: _resolve_value(target_section, k, raw_sections, cache, set()) for k in raw_sections[target_section]}
