def optional_choice(value, choices):
    if value is None:
        return True
    return any(type(option) is type(value) and option == value for option in choices)
