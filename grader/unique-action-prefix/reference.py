def resolve_action(query, aliases):
    if not query:
        return None
    query = query.casefold()
    normalized = {name.casefold(): action for name, action in aliases.items()}
    if query in normalized:
        return normalized[query]
    actions = {action for name, action in normalized.items() if name.startswith(query)}
    return actions.pop() if len(actions) == 1 else None
