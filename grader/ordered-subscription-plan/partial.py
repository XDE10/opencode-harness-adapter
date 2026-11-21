def listener_order(general, specific, muted=()):
    return list(dict.fromkeys([*specific, *general]))
