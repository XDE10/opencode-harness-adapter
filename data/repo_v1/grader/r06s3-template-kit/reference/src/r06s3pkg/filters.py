from typing import Any, Callable


class FilterRegistry:
    def __init__(self) -> None:
        self._filters: dict[str, Callable[..., Any]] = {}
        self._register_defaults()

    def register(self, name: str, func: Callable[..., Any]) -> None:
        self._filters[name] = func

    def apply(self, name: str, value: Any, arg: Any = None) -> Any:
        if name not in self._filters:
            raise KeyError(f"Unknown filter: {name}")
        func = self._filters[name]
        if arg is None:
            return func(value)
        return func(value, arg)

    def _register_defaults(self) -> None:
        self.register("upper", lambda v: "" if v is None else str(v).upper())
        self.register("lower", lambda v: "" if v is None else str(v).lower())
        self.register(
            "default",
            lambda v, fallback="": fallback if (v is None or v == "") else v,
        )
        self.register(
            "truncate",
            lambda v, length: "" if v is None else str(v)[:length],
        )
        self.register(
            "add",
            lambda v, delta: (0 if v is None else v) + delta,
        )
        self.register(
            "join",
            lambda v, sep=",": sep.join(str(x) for x in (v or [])),
        )
