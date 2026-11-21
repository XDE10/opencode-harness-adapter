def elapsed_label(seconds):
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    clock = f"{minutes:02d}:{seconds:02d}"
    return f"{hours}:{clock}" if hours else clock
