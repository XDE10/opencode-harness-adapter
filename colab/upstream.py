"""CPU-only validation against the actual pinned Harbor and OpenEnv types."""

from importlib.metadata import version
import tomllib

from .contracts import PILOT, PLAN, require


def validate_schemas(bundle):
    from harbor.models.task.config import TaskConfig
    from openenv.core.harness import TrainingTrace

    versions = {name: version(name) for name in ("harbor", "openenv")}
    require(all(deployed == PLAN["runtime"][name] for name, deployed in versions.items()),
            "upstream package versions do not match the protocol")
    for task in PILOT:
        with (bundle / "tasks" / task / "task.toml").open("rb") as file:
            cfg = TaskConfig.model_validate(tomllib.load(file))
        require(cfg.verifier.environment_mode == "separate" and cfg.environment.network_mode == "no-network"
                and cfg.verifier.network_mode == "no-network",
                f"{task}: missing verifier or network isolation")
    test = TrainingTrace.model_validate({
        "schema_version": 1, "turns": [
            {"node_id": "synthetic-schema-test", "prompt_token_ids": [1, 2],
             "completion_token_ids": [3, 4], "per_token_logps": [-0.1, -0.2],
             "loss_mask": [0, 0, 1, 0]},
        ],
    })
    require(test.turns[0].loss_mask == [0, 0, 1, 0], "upstream changed mask semantics")
    return {"versions": versions, "harbor_task_configs": PILOT,
            "openenv_trace": "synthetic_schema_only", "real_capture_executed": False}
