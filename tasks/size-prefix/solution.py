def compact_size(value, binary=False):
    labels = ("B", "kB", "MB", "GB")
    unit = value
    index = 0
    while abs(unit) >= 1000 and index < len(labels) - 1:
        index += 1
        unit = value / 1000**index
    if index == 0:
        return f"{value} B"
    return f"{unit:.1f} {labels[index]}"
