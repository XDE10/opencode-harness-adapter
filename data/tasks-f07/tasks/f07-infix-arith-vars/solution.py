def _tokenize(expr: str):
    tokens = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < n and expr[j].isdigit():
                j += 1
            tokens.append(("NUM", int(expr[i:j])))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == "_"):
                j += 1
            tokens.append(("ID", expr[i:j]))
            i = j
            continue
        if ch == "/" and i + 1 < n and expr[i + 1] == "/":
            tokens.append(("OP", "//"))
            i += 2
            continue
        if ch in "+-*%^()":
            tokens.append(("PAREN" if ch in "()" else "OP", ch))
            i += 1
            continue
        raise ValueError(f"unexpected character: {ch}")
    return tokens


def eval_infix(expr, env=None):
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError("empty expression")
    bindings = {} if env is None else env
    tokens = _tokenize(expr)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def parse_expr():
        val = parse_term()
        while (tok := peek()) is not None and tok in (("OP", "+"), ("OP", "-")):
            pos_op = tok[1]
            nonlocal pos
            pos += 1
            rhs = parse_term()
            val = val + rhs if pos_op == "+" else val - rhs
        return val

    def parse_term():
        val = parse_unary()
        while (tok := peek()) is not None and tok[0] == "OP" and tok[1] in ("*", "//", "%"):
            op = tok[1]
            nonlocal pos
            pos += 1
            rhs = parse_unary()
            if op == "*":
                val = val * rhs
            elif op == "//":
                val = val // rhs
            else:
                val = val % rhs
        return val

    def parse_unary():
        tok = peek()
        if tok is not None and tok in (("OP", "+"), ("OP", "-")):
            nonlocal pos
            pos += 1
            inner = parse_unary()
            return inner if tok[1] == "+" else -inner
        return parse_power()

    def parse_power():
        val = parse_primary()
        while (tok := peek()) is not None and tok == ("OP", "^"):
            nonlocal pos
            pos += 1
            exp = parse_unary()
            if exp < 0:
                raise ValueError("negative exponent")
            val = val ** exp
        return val

    def parse_primary():
        nonlocal pos
        tok = peek()
        if tok is None:
            raise ValueError("unexpected end of expression")
        if tok[0] == "NUM":
            pos += 1
            return tok[1]
        if tok[0] == "ID":
            pos += 1
            val = bindings.get(tok[1])
            if not val:
                raise KeyError(tok[1])
            return val
        if tok == ("PAREN", "("):
            pos += 1
            val = parse_expr()
            if peek() != ("PAREN", ")"):
                raise ValueError("mismatched parentheses")
            pos += 1
            return val
        raise ValueError(f"unexpected token: {tok[1]}")

    return parse_expr()
