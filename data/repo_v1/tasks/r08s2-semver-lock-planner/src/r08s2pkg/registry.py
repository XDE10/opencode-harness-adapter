from __future__ import annotations
from dataclasses import dataclass, field
from r08s2pkg.semver import Version, ConstraintSpec


@dataclass(frozen=True)
class ReleaseManifest:
    name: str
    version: Version
    dependencies: dict[str, ConstraintSpec] = field(default_factory=dict)


class PackageRegistry:
    def __init__(self) -> None:
        self._packages: dict[str, list[ReleaseManifest]] = {}

    def register(
        self,
        name: str,
        version: str,
        dependencies: dict[str, str] | None = None,
    ) -> ReleaseManifest:
        ver = Version.parse(version)
        parsed_deps = {
            dep_name: ConstraintSpec.parse(spec_str)
            for dep_name, spec_str in (dependencies or {}).items()
        }
        manifest = ReleaseManifest(name=name, version=ver, dependencies=parsed_deps)
        releases = self._packages.setdefault(name, [])
        releases = [m for m in releases if m.version != ver]
        releases.append(manifest)
        releases.sort(key=lambda m: m.version, reverse=True)
        self._packages[name] = releases
        return manifest

    def candidates(self, name: str, constraint: ConstraintSpec) -> list[ReleaseManifest]:
        releases = self._packages.get(name, [])
        return [m for m in releases if constraint.matches(m.version)]

    def has_package(self, name: str) -> bool:
        return name in self._packages
