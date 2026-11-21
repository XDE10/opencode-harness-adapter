def module_category(module, rules, default="other"):
    matches = [prefix for prefix in rules if module.startswith(prefix)]
    return rules[max(matches, key=len)] if matches else default
