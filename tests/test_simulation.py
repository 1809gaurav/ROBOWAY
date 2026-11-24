import json
import random
from pathlib import Path

from roboway import Simulation


ROOT = Path(__file__).parent.parent


def load_scenario(name):
    return json.loads((ROOT / "scenarios" / f"{name}.json").read_text(encoding="utf-8"))


def tick_with_invariants(sim, count=1, scripted_events=()):
    applied = set()
    for _ in range(count):
        for index, event in enumerate(scripted_events):
            if event["tick"] == sim.tick_count and index not in applied:
                if event["action"] == "fail_robot":
                    sim.fail_robot(event["robot"])
                elif event["action"] == "block_cell":
                    sim.block_cell(event["x"], event["y"])
                elif event["action"] == "unblock_cell":
                    sim.unblock_cell(event["x"], event["y"])
                applied.add(index)
        previous = {robot.id: robot.pos for robot in sim.robots.values()}
        sim.tick()
        positions = [robot.pos for robot in sim.robots.values() if robot.status != "failed"]
        assert len(positions) == len(set(positions))
        for first in sim.robots.values():
            for second in sim.robots.values():
                if first.id >= second.id or first.id not in previous or second.id not in previous:
                    continue
                assert not (
                    previous[first.id] == second.pos
                    and previous[second.id] == first.pos
                    and previous[first.id] != first.pos
                )
        owners = [job.owner for job in sim.jobs.values() if job.owner]
        assert len(owners) == len(set(owners))
        carried = [robot.carrying for robot in sim.robots.values() if robot.carrying]
        assert len(carried) == len(set(carried))
        assert sim.metrics.invariant_violations == 0


def minimal_scenario(robots, pickup, drop, width=6, height=3):
    return {
        "id": "test",
        "seed": 3,
        "grid": {
            "width": width,
            "height": height,
            "obstacles": [],
            "blocked": [],
            "pickups": [{"id": "P", "pos": pickup}],
            "drops": [{"id": "D", "pos": drop}],
        },
        "robots": [{"id": robot_id, "start": pos} for robot_id, pos in robots],
        "jobs": [{"pickup_id": "P", "drop_id": "D", "at_tick": 0}],
    }


def test_snapshot_has_contract_shape():
    sim = Simulation()
    sim.load_scenario(load_scenario("narrow_passage"))
    state = sim.snapshot()
    assert set(state) == {
        "tick", "status", "speed", "scenario_id", "grid", "robots", "jobs",
        "reservations_count", "deadlock", "metrics", "events_tail",
    }
    assert set(state["robots"][0]) == {"id", "pos", "status", "carrying", "job_id", "path", "wait_ticks"}
    assert set(state["jobs"][0]) == {
        "id", "pickup_id", "drop_id", "state", "owner", "created_tick", "assigned_tick",
        "picked_tick", "delivered_tick", "history",
    }
    assert set(state["metrics"]) == {
        "completed_jobs", "total_jobs", "total_wait_ticks", "avg_wait_ticks_per_job",
        "congestion", "planner_rejections", "conflicts_prevented", "invariant_violations",
        "deadlocks_resolved", "reassignments",
    }


def test_reservations_reject_vertex_and_swap():
    from roboway.reservation import ReservationTable

    table = ReservationTable()
    table.reserve_path("R1", [(0, 0, 0), (1, 0, 1)])
    assert not table.is_free(1, 0, 1, "R2")
    assert not table.edge_free(1, 0, 0, 0, 1, "R2")
    assert table.is_free(1, 0, 1, "R1")


def test_idle_robot_reserves_its_parking_cell_through_the_horizon():
    sim = Simulation()
    sim.load_scenario(minimal_scenario([("R1", [2, 1])], [0, 0], [1, 0]))
    table = sim._build_reservations()
    assert not table.is_free(2, 1, sim.tick_count + 60, "R2")


def test_space_time_planner_routes_around_reservation():
    from roboway.models import Grid
    from roboway.planner import plan
    from roboway.reservation import ReservationTable

    grid = Grid(3, 2)
    table = ReservationTable()
    table.reserve_path("R1", [(1, 0, 0), (1, 1, 1), (1, 0, 2)])
    route = plan(grid, table, "R2", (0, 0), (2, 0), 0)
    assert route is not None
    assert all(table.is_free(x, y, tick, "R2") for x, y, tick in route)


def test_planner_rejections_are_separate_from_runtime_conflict_events():
    scenario = load_scenario("narrow_passage")
    sim = Simulation()
    sim.load_scenario(scenario)
    sim.start()
    tick_with_invariants(sim, 50, scenario.get("scripted_events", ()))
    metrics = sim.snapshot()["metrics"]
    conflict_events = sum(event.type == "CONFLICT_AVOIDED" for event in sim.events.events)
    assert metrics["planner_rejections"] > 0
    assert metrics["conflicts_prevented"] == conflict_events


def test_waiting_jobs_distinguish_busy_robots_from_unreachable_pickups():
    busy = minimal_scenario([("R1", [0, 1])], [1, 1], [5, 1])
    busy["jobs"].append({"pickup_id": "P", "drop_id": "D", "at_tick": 0})
    sim = Simulation()
    sim.load_scenario(busy)
    sim.start()
    tick_with_invariants(sim, 12)
    waiting_events = [event for event in sim.events.events if event.type == "JOB_WAITING" and event.job == "J2"]
    assert len(waiting_events) == 1
    assert waiting_events[0].msg == "J2 is waiting: no idle robot available"
    assert not any(event.type == "JOB_UNREACHABLE" and event.job == "J2" for event in sim.events.events)

    unreachable = minimal_scenario([("R1", [0, 1])], [3, 1], [3, 2], width=5, height=3)
    unreachable["grid"]["obstacles"] = [[2, y] for y in range(3)]
    sim.load_scenario(unreachable)
    sim.start()
    tick_with_invariants(sim, 5)
    failures = [event for event in sim.events.events if event.type == "JOB_UNREACHABLE" and event.job == "J1"]
    assert len(failures) == 1
    assert "no path exists" in failures[0].msg


def test_randomized_runs_have_no_vertex_or_swap_conflicts():
    for seed in range(100):
        rng = random.Random(seed)
        count = rng.randint(3, 5)
        starts = [(0, index) for index in range(count)]
        pickups = [{"id": f"P{i}", "pos": list(pos)} for i, pos in enumerate(starts)]
        drops = [{"id": f"D{i}", "pos": [5, count - i - 1]} for i in range(count)]
        scenario = {
            "id": f"random-{seed}",
            "seed": seed,
            "grid": {"width": 6, "height": 6, "obstacles": [], "blocked": [], "pickups": pickups, "drops": drops},
            "robots": [{"id": f"R{i}", "start": list(pos)} for i, pos in enumerate(starts)],
            "jobs": [{"pickup_id": f"P{i}", "drop_id": f"D{i}", "at_tick": 0} for i in range(count)],
        }
        sim = Simulation()
        sim.load_scenario(scenario)
        sim.start()
        tick_with_invariants(sim, 18)


def test_corridor_jobs_complete_without_swap():
    scenario = minimal_scenario([("R1", [0, 1]), ("R2", [6, 1])], [0, 1], [6, 1], 7, 3)
    scenario["grid"]["obstacles"] = [[x, 0] for x in range(7)] + [[x, 2] for x in (0, 1, 5, 6)]
    scenario["grid"]["pickups"].append({"id": "P2", "pos": [6, 1]})
    scenario["grid"]["drops"].append({"id": "D2", "pos": [0, 1]})
    scenario["jobs"] = [{"pickup_id": "P", "drop_id": "D", "at_tick": 0}, {"pickup_id": "P2", "drop_id": "D2", "at_tick": 0}]
    sim = Simulation()
    sim.load_scenario(scenario)
    sim.start()
    tick_with_invariants(sim, 40)
    assert sum(job.state == "Delivered" for job in sim.jobs.values()) == 2


def test_scenarios_are_deterministic_and_narrow_passage_resolves():
    for name in ("narrow_passage", "failed_robot", "blocked_aisle"):
        histories = []
        for _ in range(2):
            sim = Simulation()
            scenario = load_scenario(name)
            sim.load_scenario(scenario)
            sim.start()
            tick_with_invariants(sim, 80, scenario.get("scripted_events", ()))
            histories.append([event.to_dict() for event in sim.events.events])
        assert histories[0] == histories[1]
        assert all(job.state == "Delivered" for job in sim.jobs.values())
        assert all(
            sum(event.type == "DELIVERED" and event.job == job.id for event in sim.events.events) == 1
            for job in sim.jobs.values()
        )
        if name == "blocked_aisle":
            assert any(event.type in ("PATH_PLANNED", "REPLAN") for event in sim.events.events)
        if name == "failed_robot":
            assert any(event.type == "JOB_REASSIGNED" for event in sim.events.events)
            assert any(event.type == "PACKAGE_STRANDED" for event in sim.events.events)
    types = [event["type"] for event in histories[0]]
    narrow = Simulation()
    scenario = load_scenario("narrow_passage")
    narrow.load_scenario(scenario)
    narrow.start()
    tick_with_invariants(narrow, 100, scenario.get("scripted_events", ()))
    types = [event["type"] for event in narrow.events_since(0)]
    assert "DEADLOCK_DETECTED" in types
    assert "DEADLOCK_RESOLVED" in types
    assert all(job.state == "Delivered" for job in narrow.jobs.values())


def test_block_replans_without_resetting_tick():
    sim = Simulation()
    scenario = minimal_scenario([("R1", [0, 1])], [2, 1], [5, 1])
    sim.load_scenario(scenario)
    sim.start()
    sim.tick()
    robot = sim.robots["R1"]
    target = next(step[:2] for step in robot.path[1:] if step[:2] != robot.pos)
    old_tick = sim.tick_count
    result = sim.block_cell(*target)
    assert result["ok"] is True
    sim.tick()
    assert sim.tick_count == old_tick + 1
    assert any(event.type in ("PATH_PLANNED", "REPLAN") for event in sim.events.events)


def test_replan_event_reports_old_remaining_path_length():
    sim = Simulation()
    sim.load_scenario(minimal_scenario([("R1", [0, 1])], [4, 1], [5, 1]))
    sim.start()
    sim.tick()
    robot = sim.robots["R1"]
    assert len(robot.path) > 1
    old_steps = len(robot.path) - 1
    assert sim.block_cell(*robot.path[1][:2])["ok"]
    sim.tick()
    event = next(event for event in sim.events.events if event.type == "REPLAN" and event.robot == "R1")
    assert "new path" in event.msg
    assert f"was {old_steps}" in event.msg


def test_path_planned_events_never_report_zero_step_routes():
    scenario = minimal_scenario([("R1", [1, 1])], [1, 1], [5, 1])
    sim = Simulation()
    sim.load_scenario(scenario)
    sim.start()
    tick_with_invariants(sim, 12)
    path_events = [event for event in sim.events.events if event.type in ("PATH_PLANNED", "REPLAN")]
    assert path_events
    assert all(len(event.data["path"]) > 1 for event in path_events)


def test_heatmap_counts_waits_and_moving_occupancy_only():
    from roboway.metrics import update_metrics
    from roboway.models import Grid, Metrics, Robot
    from roboway.reservation import ReservationTable

    grid = Grid(5, 3)
    robots = [
        Robot("R1", (0, 0), status="idle"),
        Robot("R2", (1, 0), status="moving", job_id="J2"),
        Robot("R3", (2, 0), status="waiting", job_id="J3"),
        Robot("R4", (3, 0), status="failed"),
    ]
    metrics = Metrics()
    update_metrics(metrics, grid, robots, ReservationTable(), 0)
    assert metrics.heatmap == {(1, 0): 1, (2, 0): 1}
    assert metrics.total_wait_ticks == 1


def test_failure_before_pickup_reassigns_and_delivers_once():
    scenario = minimal_scenario([("R1", [0, 1]), ("R2", [0, 2])], [5, 1], [5, 2])
    sim = Simulation()
    sim.load_scenario(scenario)
    sim.start()
    sim.tick()
    assert sim.jobs["J1"].state == "Assigned"
    assert sim.fail_robot("R1")["ok"]
    sim.tick()
    tick_with_invariants(sim, 35)
    assert sim.jobs["J1"].state == "Delivered"
    assert len([e for e in sim.events.events if e.type == "DELIVERED" and e.job == "J1"]) == 1
    assert any(e.type == "JOB_REASSIGNED" for e in sim.events.events)


def test_failure_after_pickup_recovers_and_delivers_once():
    scenario = minimal_scenario([("R1", [0, 1]), ("R2", [0, 0])], [0, 1], [5, 1])
    sim = Simulation()
    sim.load_scenario(scenario)
    sim.start()
    sim.tick()
    assert sim.jobs["J1"].state == "PickedUp"
    assert sim.fail_robot("R1")["carrying_job"] == "J1"
    sim.tick()
    tick_with_invariants(sim, 35)
    assert sim.jobs["J1"].state == "Delivered"
    assert "Stranded" in sim.jobs["J1"].history
    assert len([e for e in sim.events.events if e.type == "DELIVERED" and e.job == "J1"]) == 1


def test_delivered_job_unchanged_after_later_failure():
    scenario = minimal_scenario([("R1", [0, 1]), ("R2", [0, 0])], [0, 1], [2, 1], 4, 3)
    sim = Simulation()
    sim.load_scenario(scenario)
    sim.start()
    tick_with_invariants(sim, 10)
    delivered = sim.jobs["J1"].to_dict()
    sim.fail_robot("R2")
    sim.tick()
    assert sim.jobs["J1"].to_dict() == delivered


def test_add_job_while_running_assigns_and_edit_validation_is_dry_run():
    sim = Simulation()
    scenario = minimal_scenario([("R1", [0, 1])], [1, 1], [4, 1])
    scenario["jobs"] = []
    sim.load_scenario(scenario)
    sim.start()
    job_id = sim.add_job("P", "D")
    sim.tick()
    assert sim.jobs[job_id].owner == "R1"
    before = sim.snapshot()
    result = sim.validate_job_edit(job_id, "P", "D")
    after = sim.snapshot()
    assert result["ok"] and result["result"] in ("valid", "conflict")
    assert before == after
