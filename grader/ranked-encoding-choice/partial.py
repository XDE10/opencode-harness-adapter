def choose_encoding(candidates, threshold):
    chosen = None
    best = threshold
    for name, confidence in candidates:
        if name and confidence is not None and confidence >= best:
            chosen, best = name, confidence
    return chosen
