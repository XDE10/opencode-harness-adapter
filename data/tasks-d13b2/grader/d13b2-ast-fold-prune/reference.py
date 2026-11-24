def lit(value):
    if value is None or isinstance(value, (bool, int, str)):
        return {"kind": "lit", "value": value}
    raise ValueError

def is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)

def truth(value):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if is_int(value):
        return value != 0
    if isinstance(value, str):
        return value != ""
    raise ValueError

def fold_expr(node):
    if not isinstance(node, dict):
        raise ValueError
    kind = node.get("kind")
    if kind == "lit":
        return lit(node["value"])
    if kind == "var":
        name = node["name"]
        if not isinstance(name, str):
            raise ValueError
        return {"kind": "var", "name": name}
    if kind == "not":
        expr = fold_expr(node["expr"])
        if expr["kind"] == "lit":
            return lit(not truth(expr["value"]))
        return {"kind": "not", "expr": expr}
    if kind == "neg":
        expr = fold_expr(node["expr"])
        if expr["kind"] == "lit" and is_int(expr["value"]):
            return lit(-expr["value"])
        return {"kind": "neg", "expr": expr}
    if kind == "bin":
        op = node["op"]
        if op not in ("+", "-", "*", "//", "==", "and", "or"):
            raise ValueError
        left = fold_expr(node["left"])
        if op in ("and", "or"):
            if left["kind"] == "lit":
                t = truth(left["value"])
                if (op == "and" and not t) or (op == "or" and t):
                    return left
                return fold_expr(node["right"])
            right = fold_expr(node["right"])
            return {"kind": "bin", "op": op, "left": left, "right": right}
        right = fold_expr(node["right"])
        if left["kind"] == "lit" and right["kind"] == "lit":
            a = left["value"]
            b = right["value"]
            if op == "==":
                return lit(type(a) is type(b) and a == b)
            if is_int(a) and is_int(b):
                if op == "+":
                    return lit(a + b)
                if op == "-":
                    return lit(a - b)
                if op == "*":
                    return lit(a * b)
                if b == 0:
                    raise ZeroDivisionError
                return lit(a // b)
        return {"kind": "bin", "op": op, "left": left, "right": right}
    if kind == "if":
        cond = fold_expr(node["cond"])
        if cond["kind"] == "lit":
            return fold_expr(node["then"] if truth(cond["value"]) else node["else"])
        then = fold_expr(node["then"])
        other = fold_expr(node["else"])
        return {"kind": "if", "cond": cond, "then": then, "else": other}
    raise ValueError
