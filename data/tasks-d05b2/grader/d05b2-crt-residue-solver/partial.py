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

def _egcd(a, b):
    old_r, r = a, b
    old_s, s = 1, 0
    old_t, t = 0, 1
    while r:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_s, s = s, old_s - q * s
        old_t, t = t, old_t - q * t
    return old_r, old_s, old_t

def _mod_inv(a, m):
    g, x, _ = _egcd(a, m)
    if g != 1:
        raise ValueError("not invertible")
    return x % m

def crt(congruences):
    _validate_sequence(congruences)
    x = 0
    mod = 1
    for pair in congruences:
        r, m = _check_pair(pair)
        g = math.gcd(mod, m)
        lcm = mod // g * m
        m2 = m // g
        if m2 == 1:
            t = 0
        else:
            coeff = (mod // g) % m2
            inv = _mod_inv(coeff, m2)
            t = (((r - x) // g) * inv) % m2
        x = (x + mod * t) % lcm
        mod = lcm
    return [x, mod]
