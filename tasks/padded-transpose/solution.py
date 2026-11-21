def transpose_padded(rows, fill=None):
    return [list(column) for column in zip(*rows)]
