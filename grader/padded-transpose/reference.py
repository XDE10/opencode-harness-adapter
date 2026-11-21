def transpose_padded(rows, fill=None):
    width = max((len(row) for row in rows), default=0)
    return [[row[index] if index < len(row) else fill for row in rows]
            for index in range(width)]
