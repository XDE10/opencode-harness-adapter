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
            if not self.registry.has_package(pkg):
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
            next_assigned = dict(assigned)
            next_assigned[next_pkg] = candidate
            next_constraints = dict(constraints)

            conflict = False
            for dep_name, dep_spec in candidate.dependencies.items():
                if dep_name in next_constraints:
                    next_constraints[dep_name] = next_constraints[dep_name].combine(dep_spec)
                else:
                    next_constraints[dep_name] = dep_spec
                if (
                    dep_name in next_assigned
                    and not next_constraints[dep_name].matches(next_assigned[dep_name].version)
                ):
                    conflict = True
                    break

            if not conflict:
                result = self._backtrack(next_constraints, next_assigned)
                if result is not None:
                    return result

        return None
