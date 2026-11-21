def option_summary(options):
    short, long = [], []
    for option in options:
        (long if option.startswith("--") else short).append(option)
    return [", ".join(short + long), any(option.startswith("/") for option in options)]
