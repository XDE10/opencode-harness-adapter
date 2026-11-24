from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class FilterSpec:
    name: str
    arg: str | None = None


@dataclass(frozen=True)
class RegisteredFilter:
    func: Callable[..., Any]
    invalidate_empty: bool = False


class FilterRegistry:
    def __init__(self) -> None:
        self._filters: dict[str, RegisteredFilter] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register("upper", lambda v: str(v).upper(), invalidate_empty=True)
        self.register("lower", lambda v: str(v).lower(), invalidate_empty=True)
        self.register("strip", lambda v: str(v).strip(), invalidate_empty=True)
        self.register(
            "default",
            lambda v, fallback="": fallback if (v is None or v == "") else v,
            invalidate_empty=False,
        )
        self.register(
            "prefix",
            lambda v, pre="": f"{pre}{v}",
            invalidate_empty=True,
        )
        self.register(
            "suffix",
            lambda v, suf="": f"{v}{suf}",
            invalidate_empty=True,
        )
        self.register(
            "replace",
            lambda v, pair="": self._apply_replace(v, pair),
            invalidate_empty=True,
        )

    @staticmethod
    def _apply_replace(value: Any, pair: str) -> str:
        if "->" not in pair:
            return str(value)
        old, new = pair.split("->", 1)
        return str(value).replace(old, new)

    def register(
        self,
        name: str,
        func: Callable[..., Any],
        *,
        invalidate_empty: bool = False,
    ) -> None:
        self._filters[name] = RegisteredFilter(
            func=func,
            invalidate_empty=invalidate_empty,
        )

    def apply_pipeline(self, value: Any, specs: list[FilterSpec]) -> Any:
        current = value
        for spec in specs:
            if spec.name not in self._filters:
                raise KeyError(f"Unknown filter: {spec.name}")
            entry = self._filters[spec.name]
            if entry.invalidate_empty and (current is None or current == ""):
                return ""
            if spec.arg is not None:
                current = entry.func(current, spec.arg)
            else:
                current = entry.func(current)
        return current
