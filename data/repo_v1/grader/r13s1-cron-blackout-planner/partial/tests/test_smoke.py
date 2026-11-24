from datetime import datetime
from cronplan import BlackoutWindow, JobSpec, SchedulePlanner, parse_cron


def test_parse_simple_every_15_minutes():
    sched = parse_cron("*/15 * * * *")
    assert sched.minutes == frozenset({0, 15, 30, 45})
    assert sched.matches(datetime(2025, 3, 10, 12, 15))
    assert not sched.matches(datetime(2025, 3, 10, 12, 16))


def test_basic_single_minute_planning():
    planner = SchedulePlanner(max_concurrent=1)
    planner.register_job(JobSpec(job_id="heartbeat", cron_expr="0,30 * * * *", duration_minutes=1))
    runs = planner.plan_horizon(
        datetime(2025, 3, 10, 8, 0),
        datetime(2025, 3, 10, 9, 0),
    )
    assert [r.start for r in runs] == [
        datetime(2025, 3, 10, 8, 0),
        datetime(2025, 3, 10, 8, 30),
        datetime(2025, 3, 10, 9, 0),
    ]


def test_priority_tie_breaking_same_minute():
    planner = SchedulePlanner(max_concurrent=1)
    planner.register_job(JobSpec(job_id="low", cron_expr="0 10 * * *", duration_minutes=1, priority=1))
    planner.register_job(JobSpec(job_id="high", cron_expr="0 10 * * *", duration_minutes=1, priority=10))
    runs = planner.plan_horizon(
        datetime(2025, 3, 10, 10, 0),
        datetime(2025, 3, 10, 10, 0),
    )
    assert len(runs) == 1
    assert runs[0].job_id == "high"
