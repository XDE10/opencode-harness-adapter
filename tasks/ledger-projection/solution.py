def project_rows(rows, columns, default=None):
    return [[row[index] for index in columns if index < len(row)] for row in rows]
