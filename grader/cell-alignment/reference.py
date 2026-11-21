def align_cell(text, width, alignment):
    padding = max(0, width - len(text))
    left = {"l": 0, "r": padding, "c": padding // 2}[alignment]
    return " " * left + text + " " * (padding - left)
