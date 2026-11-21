def module_category(module, rules, default="other"):
    return rules.get(module.split(".")[0], default)
