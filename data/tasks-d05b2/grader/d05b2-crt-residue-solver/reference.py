import math

def _validate_sequence(value):
    if type(value) is not list:
        raise ValueError("bad input")

def _check_pair(pair):
    if type(pair) is not list or len(pair) != 2:
        raise ValueError("bad congruence")
    a, m = pair
    if type(a) is not int or type(m) is not int:
        raise ValueError("bad congruence")
    if m <= 0:
        raise ValueError("bad modulus")
    return a % m, m

def crt(congruences):
    _validate_sequence(congruences)
    x = 0
    mod = 1
    for pair in congruences:
        r, m = _check_pair(pair)
        g = math.gcd(mod, m)
        diff = r - x
        if diff % g != 0:
            raise ValueError("inconsistent congruences")
        lcm = mod // g * m
        m2 = m // g
        if m2 == 1:
            t = 0
        else:
            coeff = (mod // g) % m2
            inv = pow(coeff, -1, m2)
            t = (diff // g * inv) % m2
        x = (x + mod * t) % lcm
        mod = lcm
    return [x, mod]
