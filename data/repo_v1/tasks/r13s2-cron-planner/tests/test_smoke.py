from datetime import datetime

from r13s2cron import BlackoutWindow, JobDef, SchedulePlanner, parse_cron


def test_basic_cron_parse_and_match() -> None:
    spec = parse_cron("*/15 2 * *")
    assert spec.matches(datetime(2025, 5, 10, 2, 0))
    assert spec.matches(datetime(2025, 5, 10, 2, 45))
    assert not spec.matches(datetime(2025, 5, 10, 3, 0))


def test_basic_planner_single_job() -> None:
    planner = SchedulePlanner()
    planner.register_job(JobDef("etl-hourly", "0 * * *", "db-primary", priority=5))
    runs = planner.plan_window(
        datetime(2025, 5, 10, 1, 0),
        datetime(2025, 5, 10, 2, 30),
    )
    assert [r.scheduled_at for r in runs] == [
        datetime(2025, 5, 10, 1, 0),
        datetime(2025, 5, 10, 2, 0),
    ]


def test_blackout_blocks_interior_timestamp() -> None:
    planner = SchedulePlanner()
    planner.register_job(JobDef("sync", "0,30 * * *", "cluster-a", priority=1))
    planner.add_blackout(
        BlackoutWindow(
            name="maint",
            start=datetime(2025, 5, 10, 0, 50),
            end=datetime(2025, 5, 10, 1, 15),
            resources=frozenset({"cluster-a"}),
        )
    )
    runs = planner.plan_window(
        datetime(2025, 5, 10, 0, 30),
        datetime(2025, 5, 10, 1, 30),
    )
    assert [r.scheduled_at for r in runs] == [
        datetime(2025, 5, 10, 0, 30),
        datetime(2025, 5, 10, 1, 30),
    ]
