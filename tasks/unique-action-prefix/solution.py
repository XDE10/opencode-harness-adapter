def resolve_action(query, aliases):
    query = query.casefold()
    for name, action in aliases.items():
        if name.casefold().startswith(query):
            return action
    return None
