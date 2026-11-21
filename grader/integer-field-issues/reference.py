def invalid_integer_positions(values, nullable=False):
    return [
        index for index, value in enumerate(values)
        if type(value) is not int and not (nullable and value is None)
    ]
