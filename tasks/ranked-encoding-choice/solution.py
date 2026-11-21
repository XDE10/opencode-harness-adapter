def choose_encoding(candidates, threshold):
    for name, confidence in candidates:
        if name and confidence is not None and confidence >= threshold:
            return name
    return None
