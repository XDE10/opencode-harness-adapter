def release_label(parts, minimum=2):
    normalized = list(parts)
    while len(normalized) > 2 and normalized[-1] == 0:
        normalized.pop()
    normalized.extend([0] * (minimum - len(normalized)))
    return ".".join(str(part) for part in normalized)
