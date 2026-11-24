"""Pluggable coding agent harnesses (OpenCode 2.2.7 & Pi coding agent)."""
from .opencode import OpenCodeHarness
from .pi import PiHarness

REGISTRY = {
    "opencode": OpenCodeHarness,
    "pi": PiHarness,
}


def get_harness(name: str = "opencode"):
    key = (name or "opencode").lower()
    if key not in REGISTRY:
        raise ValueError(f"Unknown harness {name!r}; expected one of {sorted(REGISTRY)}")
    return REGISTRY[key]()
