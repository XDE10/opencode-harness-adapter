from __future__ import annotations
from r08s2pkg.semver import Version, ConstraintSpec
from r08s2pkg.registry import PackageRegistry, ReleaseManifest


class ResolutionConflictError(Exception):
    pass


class LockfilePlanner:
    def __init__(self, registry: PackageRegistry) -> None:
        self.registry = registry

    def resolve(self, root_requirements: dict[str, str]) -> dict[str, str]:
        constraints: dict[str, ConstraintSpec] = {
            pkg: ConstraintSpec.parse(spec)
            for pkg, spec in root_requirements.items()
        }
        assigned: dict[str, ReleaseManifest] = {}

        solution = self._backtrack(constraints, assigned)
        if solution is None:
            raise ResolutionConflictError("Unable to satisfy dependency constraints")

        return {pkg: str(manifest.version) for pkg, manifest in sorted(solution.items())}

    def _backtrack(
        self,
        constraints: dict[str, ConstraintSpec],
        assigned: dict[str, ReleaseManifest],
    ) -> dict[str, ReleaseManifest] | None:
        for pkg, spec in constraints.items():
            if pkg not in self.registry._packages:
                return None
            if pkg in assigned and not spec.matches(assigned[pkg].version):
                return None

        unassigned = sorted(pkg for pkg in constraints if pkg not in assigned)
        if not unassigned:
            return dict(assigned)

        next_pkg = unassigned[0]
        candidates = self.registry.candidates(next_pkg, constraints[next_pkg])
        if not candidates:
            return None

        for candidate in candidates:
            assigned[next_pkg] = candidate
            conflict = False
            for dep_name, dep_spec in candidate.dependencies.items():
                if dep_name in constraints:
                    constraints[dep_name] = constraints[dep_name].combine(dep_spec)
                else:
                    constraints[dep_name] = dep_spec
                if dep_name in assigned and not constraints[dep_name].matches(assigned[dep_name].version):
                    conflict = True
                    break

            if not conflict:
                result = self._backtrack(constraints, assigned)
                if result is not None:
                    return result

        return None
