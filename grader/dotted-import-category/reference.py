def module_category(module, rules, default="other"):
    prefix = module
    while prefix:
        if prefix in rules:
            return rules[prefix]
        prefix = prefix.rpartition(".")[0]
    return default
