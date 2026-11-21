def compact_size(value, binary=False):
    base = 1024 if binary else 1000
    labels = ("B", "KiB", "MiB", "GiB") if binary else ("B", "kB", "MB", "GB")
    index = 0
    while abs(value) >= base ** (index + 1) and index < len(labels) - 1:
        index += 1
    if index == 0:
        return f"{value} B"
    return f"{value / base**index:.1f} {labels[index]}"
