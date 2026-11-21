def elapsed_label(seconds):
    whole = int(seconds)
    seconds = abs(whole) % 60
    minutes = abs(whole) // 60 % 60
    hours = abs(whole) // 3600
    sign = "-" if whole < 0 else ""
    clock = f"{minutes:02d}:{seconds:02d}"
    return sign + (f"{hours}:{clock}" if hours else clock)
