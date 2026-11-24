from __future__ import annotations
from dataclasses import dataclass, field
from r08s3pkg.semver import Version, ConstraintSpec


@dataclass(frozen=True)
class Release:
    name: str
    version: Version
    dependencies: dict[str, str] = field(default_factory=dict)

    def parsed_dependencies(self) -> dict[str, ConstraintSpec]:
        return {
            dep_name: ConstraintSpec.parse(spec_str)
            for dep_name, spec_str in self.dependencies.items()
        }


class PackageRegistry:
    def __init__(self) -> None:
        self._releases: dict[str, list[Release]] = {}

    def register(
        self,
        name: str,
        version: str | Version,
        dependencies: dict[str, str] | None = None,
    ) -> Release:
        ver = Version.parse(version) if isinstance(version, str) else version
        release = Release(
            name=name,
            version=ver,
            dependencies=dict(dependencies or {}),
        )
        bucket = self._releases.setdefault(name, [])
        bucket.append(release)
        bucket.sort(key=lambda r: r.version, reverse=True)
        return release

    def candidates(self, name: str, specs: list[ConstraintSpec]) -> list[Release]:
        releases = self._releases.get(name, [])
        return [
            rel
            for rel in releases
            if all(spec.matches(rel.version) for spec in specs)
        ]

    def get_release(self, name: str, version: Version) -> Release:
        for rel in self._releases.get(name, []):
            if rel.version == version:
                return rel
        raise KeyError(f"Release {name}@{version} not found")
