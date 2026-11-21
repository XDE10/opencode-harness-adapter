def invalid_integer_positions(values, nullable=False):
    return [index for index, value in enumerate(values) if not isinstance(value, int)]
