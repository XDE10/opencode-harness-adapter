from r03s3pkg.models import NodeSpec, WorkflowSpec


def _parse_options(raw_opts: str) -> tuple[int, bool]:
    retries = 0
    allow_failure = False
    for item in raw_opts.split(","):
        part = item.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError(f"Malformed option: {part!r}")
        key, val = [x.strip() for x in part.split("=", 1)]
        if key == "retries":
            retries = int(val)
            if retries < 0:
                raise ValueError("retries must be non-negative")
        elif key == "allow_failure":
            if val.lower() == "true":
                allow_failure = True
            elif val.lower() == "false":
                allow_failure = False
            else:
                raise ValueError(f"Invalid boolean for allow_failure: {val!r}")
        else:
            raise ValueError(f"Unknown option: {key!r}")
    return retries, allow_failure


def parse_workflow(dsl_text: str) -> WorkflowSpec:
    nodes: dict[str, NodeSpec] = {}
    for raw_line in dsl_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        opts_part = ""
        if "|" in line:
            line, opts_part = line.split("|", 1)
            line = line.strip()

        deps: tuple[str, ...] = ()
        if "->" in line:
            node_id_raw, deps_raw = line.split("->", 1)
            node_id = node_id_raw.strip()
            dep_list = [d.strip() for d in deps_raw.split(",") if d.strip()]
            deps = tuple(dict.fromkeys(dep_list))
        else:
            node_id = line.strip()

        if not node_id:
            raise ValueError("Missing node_id in workflow line")
        if node_id in nodes:
            raise ValueError(f"Duplicate node_id: {node_id!r}")

        retries = 0
        allow_failure = False
        if opts_part:
            retries, allow_failure = _parse_options(opts_part)

        nodes[node_id] = NodeSpec(
            node_id=node_id,
            dependencies=deps,
            retries=retries,
            allow_failure=allow_failure,
        )

    _validate_graph(nodes)
    return WorkflowSpec(nodes=nodes)


def _validate_graph(nodes: dict[str, NodeSpec]) -> None:
    for nid, spec in nodes.items():
        for dep in spec.dependencies:
            if dep not in nodes:
                raise ValueError(f"Node {nid!r} depends on unknown node {dep!r}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(current: str) -> None:
        if current in visiting:
            raise ValueError(f"Cycle detected involving node {current!r}")
        if current in visited:
            return
        visiting.add(current)
        for dep in nodes[current].dependencies:
            dfs(dep)
        visiting.remove(current)
        visited.add(current)

    for nid in nodes:
        if nid not in visited:
            dfs(nid)
