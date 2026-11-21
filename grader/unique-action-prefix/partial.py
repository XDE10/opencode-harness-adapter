def resolve_action(query, aliases):
    if not query:
        return None
    query = query.casefold()
    normalized = {name.casefold(): action for name, action in aliases.items()}
    if query in normalized:
        return normalized[query]
    matches = [action for name, action in normalized.items() if name.startswith(query)]
    return matches[0] if len(matches) == 1 else None
