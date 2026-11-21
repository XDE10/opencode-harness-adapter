def unique_labels(labels, ignore_case=False):
    found = set()
    result = []
    for label in labels:
        key = label.lower() if ignore_case else label
        if key not in found:
            result.append(label)
            found.add(key)
    return result
