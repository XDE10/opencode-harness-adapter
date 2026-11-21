def rename_fields(event, mapping):
    unchanged = {name: value for name, value in event.items() if name not in mapping}
    renamed = {mapping[name]: value for name, value in event.items() if name in mapping}
    return renamed | unchanged
