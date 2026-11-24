from __future__ import annotations
from dataclasses import dataclass
from r08s3pkg.semver import Version, ConstraintSpec
from r08s3pkg.registry import PackageRegistry, Release


class ResolutionConflictError(Exception):
    pass


@dataclass(frozen=True)
class LockPlan:
    selected: dict[str, Release]

    def versions(self) -> dict[str, str]:
        return {name: str(rel.version) for name, rel in sorted(self.selected.items())}

    def install_order(self) -> list[tuple[str, Version]]:
        remaining = set(self.selected.keys())
        ordered: list[tuple[str, Version]] = []
        installed: set[str] = set()

        while remaining:
            ready = sorted(
                pkg
                for pkg in remaining
                if all(dep in installed for dep in self.selected[pkg].dependencies)
            )
            if not ready:
                raise ResolutionConflictError("Cyclic dependency detected in lock plan")
            chosen = ready[0]
            ordered.append((chosen, self.selected[chosen].version))
            installed.add(chosen)
            remaining.remove(chosen)
        return ordered


class DependencyResolver:
    def __init__(self, registry: PackageRegistry) -> None:
        self.registry = registry

    def resolve(self, root_requirements: dict[str, str]) -> LockPlan:
        constraints: dict[str, list[ConstraintSpec]] = {
            pkg: [ConstraintSpec.parse(spec)]
            for pkg, spec in root_requirements.items()
        }
        selected: dict[str, Release] = {}
        result = self._backtrack(selected, constraints)
        if result is None:
            raise ResolutionConflictError("Unable to satisfy all version constraints")
        return LockPlan(selected=result)

    def _backtrack(
        self,
        selected: dict[str, Release],
        constraints: dict[str, list[ConstraintSpec]],
    ) -> dict[str, Release] | None:
        for pkg, specs in constraints.items():
            if pkg in selected:
                if not all(s.matches(selected[pkg].version) for s in specs):
                    return None

        unresolved = sorted(pkg for pkg in constraints if pkg not in selected)
        if not unresolved:
            return dict(selected)

        next_pkg = unresolved[0]
        candidates = self.registry.candidates(next_pkg, constraints[next_pkg])

        for release in candidates:
            next_selected = dict(selected)
            next_selected[next_pkg] = release
            next_constraints = {k: list(v) for k, v in constraints.items()}
            for dep_name, dep_spec in release.parsed_dependencies().items():
                next_constraints.setdefault(dep_name, []).append(dep_spec)

            solved = self._backtrack(next_selected, next_constraints)
            if solved is not None:
                return solved

        return None
