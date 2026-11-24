class Parser:
    def __init__(self, expr, variables):
        self.s, self.variables, self.i = expr, variables, 0
        self.n, self.tok, self.val = len(expr), None, None
        self.advance()

    def advance(self):
        while self.i < self.n and self.s[self.i].isspace():
            self.i += 1
        if self.i >= self.n:
            self.tok, self.val = "EOF", None
            return
        c = self.s[self.i]
        if c.isascii() and c.isdigit():
            j = self.i
            while j < self.n and self.s[j].isascii() and self.s[j].isdigit():
                j += 1
            self.val, self.i, self.tok = int(self.s[self.i:j]), j, "INT"
            return
        if (c.isascii() and c.isalpha()) or c == "_":
            j = self.i + 1
            while j < self.n and (((self.s[j].isascii() and self.s[j].isalnum()) or self.s[j] == "_")):
                j += 1
            self.val, self.i, self.tok = self.s[self.i:j], j, "NAME"
            return
        self.i += 1
        if c in "+-*/()":
            self.tok, self.val = c, None
            return
        raise ValueError("bad character")

    def parse(self):
        value = self.expr()
        if self.tok != "EOF":
            raise ValueError("trailing input")
        return value

    def expr(self):
        value = self.mul()
        while self.tok in ("+", "-"):
            op = self.tok
            self.advance()
            right = self.mul()
            if op == "+": value += right
            else: value -= right
        return value

    def mul(self):
        value = self.unary()
        while self.tok in ("*", "/"):
            op = self.tok
            self.advance()
            right = self.unary()
            if op == "*": value *= right
            else:
                if right == 0: raise ZeroDivisionError
                value //= right
        return value

    def unary(self):
        if self.tok in ("+", "-"):
            op = self.tok
            self.advance()
            value = self.unary()
            return value if op == "+" else -value
        return self.primary()

    def primary(self):
        if self.tok == "INT":
            value = self.val
            self.advance()
            return value
        if self.tok == "NAME":
            name = self.val
            self.advance()
            return self.variables.get(name, 0)
        if self.tok == "(":
            self.advance()
            value = self.expr()
            if self.tok != ")":
                raise ValueError("missing )")
            self.advance()
            return value
        raise ValueError("unexpected token")

def eval_expr(expr, variables): return Parser(expr, variables).parse()
