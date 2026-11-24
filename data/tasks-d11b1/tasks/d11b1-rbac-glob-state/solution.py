import re


def _compile(pattern, cross_slash=True):
    parts = []
    for ch in pattern:
        if ch == "*":
            parts.append(".*" if cross_slash else "[^/]*")
        elif ch == "?":
            parts.append("." if cross_slash else "[^/]")
        else:
            parts.append(re.escape(ch))
    return re.compile("".join(parts))


def _matches(pattern, value):
    return _compile(pattern).fullmatch(value) is not None


def _policy_matches(policy, roles, action, resource):
    if roles.isdisjoint(policy["roles"]):
        return False
    if not any(_matches(p, action) for p in policy["actions"]):
        return False
    return any(_matches(p, resource) for p in policy["resources"])


def run(ops):
    policies = {}
    user_roles = {}
    results = []
    for op in ops:
        kind = op["op"]
        if kind == "add_policy":
            effect = op["effect"]
            if effect not in ("allow", "deny"):
                raise ValueError("bad effect")
            policies[op["id"]] = {
                "effect": effect,
                "roles": list(op["roles"]),
                "actions": list(op["actions"]),
                "resources": list(op["resources"]),
                "enabled": True,
            }
            results.append(None)
        elif kind == "remove_policy":
            policies.pop(op["id"], None)
            results.append(None)
        elif kind == "set_enabled":
            policies[op["id"]]["enabled"] = bool(op["enabled"])
            results.append(None)
        elif kind == "set_roles":
            user_roles[op["user"]] = set(op["roles"])
            results.append(None)
        elif kind == "add_role":
            user_roles.setdefault(op["user"], set()).add(op["role"])
            results.append(None)
        elif kind == "remove_role":
            user_roles.get(op["user"], set()).discard(op["role"])
            results.append(None)
        elif kind == "check":
            roles = user_roles.get(op["user"], set())
            for policy in policies.values():
                if not policy["enabled"]:
                    continue
                if _policy_matches(policy, roles, op["action"], op["resource"]):
                    results.append(policy["effect"] == "allow")
                    break
            else:
                results.append(False)
        else:
            raise ValueError("bad op")
    return results
