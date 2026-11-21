def parse_settings(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        fields = line.split("=")
        if len(fields) >= 2:
            result[fields[0]] = fields[1]
    return result
