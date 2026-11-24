from __future__ import annotations
from dataclasses import dataclass, field
from r08s1pkg.semver import Version, SpecSet


class ResolutionConflictError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    name: str
    version: Version
    dependencies: dict[str, SpecSet] = field(default_factory=dict)


class Registry:
    def __init__(self) -> None:
        self._releases: dict[str, list[Release]] = {}

    def add_release(
        self,
        name: str,
        version: str | Version,
        dependencies: dict[str, str] | None = None,
    ) -> Release:
        ver = Version.parse(version) if isinstance(version, str) else version
        dep_specs = {
            dep_name: SpecSet(spec_str)
            for dep_name, spec_str in (dependencies or {}).items()
        }
        release = Release(name=name, version=ver, dependencies=dep_specs)
        bucket = self._releases.setdefault(name, [])
        bucket.append(release)
        bucket.sort(key=lambda r: r.version, reverse=True)
        return release

    def candidates(self, name: str, spec: SpecSet) -> list[Release]:
        releases = self._releases.get(name, [])
        return [r for r in releases if spec.matches(r.version)]


class LockPlanner:
    def __init__(self, registry: Registry) -> None:
        self.registry = registry

    def resolve(self, root_requirements: dict[str, str]) -> dict[str, Version]:
        constraints: dict[str, SpecSet] = {
            pkg: SpecSet(spec) for pkg, spec in root_requirements.items()
        }
        pending: list[str] = list(root_requirements.keys())
        selected: dict[str, Version] = {}

        result = self._search(constraints, pending, selected)
        if result is None:
            raise ResolutionConflictError("Unable to satisfy dependency constraints")
        return dict(sorted(result.items()))

    def _search(
        self,
        constraints: dict[str, SpecSet],
        pending: list[str],
        selected: dict[str, Version],
    ) -> dict[str, Version] | None:
        while pending and pending[0] in selected:
            pkg = pending.pop(0)
            if not constraints[pkg].matches(selected[pkg]):
                return None

        if not pending:
            for pkg, ver in selected.items():
                if not constraints[pkg].matches(ver):
                    return None
            return dict(selected)

        current_pkg = pending[0]
        remaining_pending = pending[1:]
        active_spec = constraints[current_pkg]

        for candidate in self.registry.candidates(current_pkg, active_spec):
            next_selected = dict(selected)
            next_selected[current_pkg] = candidate.version
            next_pending = list(remaining_pending)

            conflict = False
            for dep_name, dep_spec in candidate.dependencies.items():
                existing = constraints.get(dep_name, SpecSet("*"))
                merged = existing.combine(dep_spec)
                constraints[dep_name] = merged
                if dep_name in next_selected:
                    if not merged.matches(next_selected[dep_name]):
                        conflict = True
                        break
                elif dep_name not in next_pending:
                    next_pending.append(dep_name)

            if conflict:
                continue

            solved = self._search(constraints, next_pending, next_selected)
            if solved is not None:
                return solved

        return None
