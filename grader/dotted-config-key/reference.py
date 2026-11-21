def lookup(config, path, default=None):
    current = config
    remaining = path
    while isinstance(current, dict):
        if remaining in current:
            return current[remaining]
        key, separator, remaining = remaining.partition(".")
        if not separator or key not in current:
            break
        current = current[key]
    return default
