def elapsed_label(seconds):
    whole = int(abs(seconds))
    remaining = whole % 60
    minutes = whole // 60 % 60
    hours = whole // 3600
    clock = f"{minutes:02d}:{remaining:02d}"
    if hours:
        clock = f"{hours}:{clock}"
    return "-" + clock if seconds < 0 else clock
