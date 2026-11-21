def option_summary(options):
    ordered = sorted(options, key=lambda option: option.startswith("--"))
    return [", ".join(ordered), any("/" in option for option in ordered)]
