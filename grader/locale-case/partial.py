def canonical_locale(tag):
    language, *parts = tag.replace("-", "_").lower().split("_")
    return "_".join([language, *(part.upper() if len(part) == 2 else part for part in parts)])
