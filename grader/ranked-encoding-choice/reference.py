def choose_encoding(candidates, threshold):
    chosen = None
    best = threshold
    for name, confidence in candidates:
        if not name or confidence is None or confidence < threshold:
            continue
        if chosen is None or confidence > best:
            chosen, best = name, confidence
    return chosen
