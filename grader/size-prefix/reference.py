def compact_size(value, binary=False):
    base = 1024 if binary else 1000
    labels = ("B", "KiB", "MiB", "GiB") if binary else ("B", "kB", "MB", "GB")
    index = 0
    while index < len(labels) - 1 and abs(value) >= base ** (index + 1):
        index += 1
    if index == 0:
        return f"{value} B"
    display = f"{value / base**index:.1f}"
    if index < len(labels) - 1 and abs(float(display)) >= base:
        index += 1
        display = f"{value / base**index:.1f}"
    return f"{display} {labels[index]}"
