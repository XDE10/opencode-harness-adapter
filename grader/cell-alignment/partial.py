def align_cell(text, width, alignment):
    if alignment == "r":
        return text.rjust(width)
    if alignment == "c":
        return text.center(width)
    return text.ljust(width)
