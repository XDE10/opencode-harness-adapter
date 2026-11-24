from __future__ import annotations

from typing import Any, Callable


class FilterRegistry:
    def __init__(self) -> None:
        self._filters: dict[str, Callable[..., Any]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register("upper", lambda val: str(val).upper())
        self.register("lower", lambda val: str(val).lower())
        self.register("strip", lambda val: str(val).strip())
        self.register(
            "default",
            lambda val, fallback="": fallback if (val is None or val == "") else val,
        )
        self.register(
            "prefix",
            lambda val, pre="": f"{pre}{val}",
        )
        self.register(
            "suffix",
            lambda val, suf="": f"{val}{suf}",
        )
        self.register(
            "join",
            lambda val, sep=",": str(sep).join(str(x) for x in val) if val is not None else "",
        )

    def register(self, name: str, func: Callable[..., Any]) -> None:
        self._filters[name] = func

    def apply(self, name: str, value: Any, arg: str | None = None) -> Any:
        if name not in self._filters:
            raise KeyError(f"Unknown filter: {name}")
        func = self._filters[name]
        if arg is None:
            return func(value)
        return func(value, arg)
