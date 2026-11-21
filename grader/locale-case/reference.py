def canonical_locale(tag):
    language, *qualifiers = tag.replace("-", "_").split("_")
    result = [language.lower()]
    for token in qualifiers:
        result.append(token.title() if len(token) == 4 else token.upper())
    return "_".join(result)
