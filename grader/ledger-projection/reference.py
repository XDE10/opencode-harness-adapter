def project_rows(rows, columns, default=None):
    return [
        [row[index] if index < len(row) else default for index in columns]
        for row in rows
    ]
