def wrap_lines(text, width):
    lines = []
    current = ""
    for word in text.split():
        joined = f"{current} {word}" if current else word
        if current and len(joined) > width:
            lines.append(current)
            current = word
        else:
            current = joined
    return lines + ([current] if current else [])
