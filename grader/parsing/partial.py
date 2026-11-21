def parse_settings(text: str) -> dict[str, str]:
    result = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key:
            raise ValueError("expected an assignment with a key")
        result[key] = value.strip()
    return result
