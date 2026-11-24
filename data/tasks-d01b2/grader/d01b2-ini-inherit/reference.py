import re

SEC_RE = re.compile(r"^[A-Za-z0-9_-]+$")
KEY_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
VAR_RE = re.compile(r"\$\{([^{}]+)\}")


def _strip_comment_and_parse_val(raw_val: str) -> str:
    s = raw_val.lstrip()
    if s.startswith('"'):
        out = []
        i = 1
        while i < len(s):
            ch = s[i]
            if ch == "\\":
                i += 1
                if i >= len(s):
                    raise ValueError("Trailing backslash")
                esc = s[i]
                if esc == '"':
                    out.append('"')
                elif esc == "\\":
                    out.append("\\")
                elif esc == "n":
                    out.append("\n")
                elif esc == "t":
                    out.append("\t")
                else:
                    raise ValueError(f"Bad escape: \\{esc}")
                i += 1
            elif ch == '"':
                rest = s[i + 1 :].strip()
                if rest and not (rest.startswith("#") or rest.startswith(";")):
                    raise ValueError("Trailing characters after closing quote")
                return "".join(out)
            else:
                out.append(ch)
                i += 1
        raise ValueError("Unclosed quote")
    else:
        for idx, ch in enumerate(s):
            if ch in ("#", ";"):
                s = s[:idx]
                break
            if ch == '"':
                raise ValueError("Unexpected quote in unquoted value")
        return s.strip()


def parse_ini(text: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    parents: dict[str, str | None] = {}
    current: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        if line.startswith("["):
            for idx, ch in enumerate(line):
                if ch in ("#", ";"):
                    line = line[:idx].strip()
                    break
            if not line.endswith("]"):
                raise ValueError("Invalid section header")
            inner = line[1:-1].strip()
            if ":" in inner:
                parts = inner.split(":")
                if len(parts) != 2:
                    raise ValueError("Invalid inheritance syntax")
                sec, par = parts[0].strip(), parts[1].strip()
                if not SEC_RE.match(sec) or not SEC_RE.match(par):
                    raise ValueError("Invalid section name")
            else:
                sec, par = inner, None
                if not SEC_RE.match(sec):
                    raise ValueError("Invalid section name")
            if sec not in sections:
                sections[sec] = {}
                parents[sec] = par
            else:
                if par is not None:
                    if parents[sec] is not None and parents[sec] != par:
                        raise ValueError("Conflicting parent declaration")
                    parents[sec] = par
            current = sec
            continue

        for idx, ch in enumerate(raw_line):
            if ch in ("#", ";"):
                raise ValueError("Comment without key=value")
            if ch == "=":
                break
        else:
            raise ValueError("Missing '=' in line")

        k_raw, v_raw = raw_line.split("=", 1)
        key = k_raw.strip()
        if not KEY_RE.match(key):
            raise ValueError(f"Invalid key: {key}")
        val = _strip_comment_and_parse_val(v_raw)
        if current is None:
            current = "default"
            sections.setdefault("default", {})
            parents.setdefault("default", None)
        sections[current][key] = val

    merged: dict[str, dict[str, str]] = {}
    for sec in sections:
        chain = []
        cur: str | None = sec
        seen_sec = set()
        while cur is not None:
            if cur in seen_sec:
                raise ValueError("Section inheritance cycle")
            if cur not in sections:
                raise ValueError(f"Unknown parent section: {cur}")
            seen_sec.add(cur)
            chain.append(cur)
            cur = parents[cur]
        combined: dict[str, str] = {}
        for ancestor in reversed(chain):
            combined.update(sections[ancestor])
        merged[sec] = combined

    memo: dict[tuple[str, str], str] = {}
    visiting: set[tuple[str, str]] = set()

    def resolve(sec: str, key: str) -> str:
        state = (sec, key)
        if state in memo:
            return memo[state]
        if state in visiting:
            raise ValueError("Variable interpolation cycle")
        if sec not in merged or key not in merged[sec]:
            raise KeyError(f"{sec}.{key}")
        visiting.add(state)

        def repl(m: re.Match) -> str:
            target = m.group(1)
            if "." in target:
                s_name, k_name = target.split(".", 1)
                if s_name in merged:
                    return resolve(s_name, k_name)
            return resolve(sec, target)

        res = VAR_RE.sub(repl, merged[sec][key])
        visiting.remove(state)
        memo[state] = res
        return res

    return {sec: {k: resolve(sec, k) for k in kvs} for sec, kvs in merged.items()}
