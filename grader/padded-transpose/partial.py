def transpose_padded(rows, fill=None):
    width = len(rows[0]) if rows else 0
    return [[row[index] if index < len(row) else fill for row in rows]
            for index in range(width)]
