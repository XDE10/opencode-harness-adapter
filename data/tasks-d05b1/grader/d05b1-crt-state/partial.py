from math import gcd


class CRTSolver:
    def __init__(self):
        self.x = 0
        self.mod = 1
        self.seen = {}

    def reset(self):
        self.x = 0
        self.mod = 1
        self.seen = {}
        return None

    def solve(self):
        return [self.x, self.mod]

    def add(self, r, m):
        rr = self._normalize(r, m)
        if m in self.seen and self.seen[m] != rr:
            raise ValueError
        self.seen[m] = rr
        self.x, self.mod = self._merge(rr, m)
        return None

    def _normalize(self, r, m):
        if type(r) is not int:
            raise ValueError
        if type(m) is not int:
            raise ValueError
        if m <= 0:
            raise ValueError
        return r % m

    def _merge(self, rr, m):
        g = gcd(self.mod, m)
        new_mod = self.mod // g * m
        step = m // g
        if step == 1:
            return self.x, new_mod
        base = self.mod // g
        factor = pow(base, -1, step)
        delta = (rr - self.x) // g
        t = (delta * factor) % step
        return (self.x + self.mod * t) % new_mod, new_mod


def run(ops):
    solver = CRTSolver()
    out = []
    for item in ops:
        op = item["op"]
        if op == "reset":
            out.append(solver.reset())
        elif op == "solve":
            out.append(solver.solve())
        elif op == "add":
            out.append(solver.add(item["r"], item["m"]))
        else:
            raise ValueError
    return out
