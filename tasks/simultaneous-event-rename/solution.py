def rename_fields(event, mapping):
    updated = dict(event)
    for source, destination in mapping.items():
        if source in updated:
            updated[destination] = updated.pop(source)
    return updated
