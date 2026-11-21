def unique_labels(labels, ignore_case=False):
    by_key = {}
    for label in labels:
        key = label.casefold() if ignore_case else label
        by_key.setdefault(key, label)
    return list(by_key.values())
