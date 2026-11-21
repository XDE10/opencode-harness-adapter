def listener_order(general, specific, muted=()):
    seen = set(muted)
    ordered = []
    for label in [*specific, *general]:
        if label not in seen:
            seen.add(label)
            ordered.append(label)
    return ordered
