def wrap_lines(text, width):
    lines = []
    for paragraph in text.splitlines():
        current = ""
        for word in paragraph.split():
            if current and len(current) + 1 + len(word) > width:
                lines.append(current)
                current = ""
            current = f"{current} {word}" if current else word
        lines.append(current)
    return lines
