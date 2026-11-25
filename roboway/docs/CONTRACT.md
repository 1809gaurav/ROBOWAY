# ROBOWAY simulation contract

Python 3.11+; the engine uses only the standard library. Coordinates are `[x, y]`, origin top-left, and movement is 4-connected. A robot occupies one cell and carries at most one package. Simulation state is in memory and ticks are deterministic for a scenario seed.

## Public facade

`Simulation` is the integration boundary:

- `load_scenario(scenario: dict) -> None`
- `start() -> None`, `pause() -> None`, `set_speed(speed: float) -> None`
- `tick() -> None` advances exactly one tick while running
- `add_job(pickup_id: str, drop_id: str) -> str`
- `validate_job_edit(job_id, pickup_id, drop_id) -> dict` is a dry run
- `edit_job(job_id, pickup_id, drop_id) -> dict`
- `block_cell(x, y) -> dict`, `unblock_cell(x, y) -> dict`
- `fail_robot(robot_id) -> dict`
- `snapshot() -> dict`, `events_since(event_id: int) -> list[dict]`

Errors use `{"ok": false, "error": "CODE", "message": "..."}`. A successful edit validation uses `{"ok": true, "result": "valid"}`; a routing conflict returns `{"ok": true, "result": "conflict", "reason": "...", "suggestion": {"pickup_id": "...", "drop_id": "..."}}`.

## Snapshot

`snapshot()` returns the following state shape (array ordering is deterministic). Paths contain `[x, y, absolute_tick]`.

```json
{
  "tick": 42,
  "status": "running",
  "speed": 1,
  "scenario_id": "narrow_passage",
  "grid": {
    "width": 12,
    "height": 7,
    "obstacles": [[0, 2]],
    "blocked": [],
    "pickups": [{"id": "P1", "pos": [1, 3]}],
    "drops": [{"id": "D1", "pos": [10, 1]}]
  },
  "robots": [{
    "id": "R1",
    "pos": [4, 3],
    "status": "idle",
    "carrying": null,
    "job_id": null,
    "path": [[4, 3, 42]],
    "wait_ticks": 2
  }],
  "jobs": [{
    "id": "J1",
    "pickup_id": "P1",
    "drop_id": "D1",
    "state": "Waiting",
    "owner": null,
    "created_tick": 0,
    "assigned_tick": null,
    "picked_tick": null,
    "delivered_tick": null,
    "history": ["Waiting"]
  }],
  "reservations_count": 18,
  "deadlock": {"active": false, "cycle": []},
  "metrics": {
    "completed_jobs": 0,
    "total_jobs": 1,
    "total_wait_ticks": 0,
    "avg_wait_ticks_per_job": null,
    "congestion": {"index": 0, "heatmap": []},
    "planner_rejections": 0,
    "conflicts_prevented": 0,
    "invariant_violations": 0,
    "deadlocks_resolved": 0,
    "reassignments": 0
  },
  "events_tail": [{
    "id": 1,
    "tick": 0,
    "type": "JOB_CREATED",
    "robot": null,
    "job": "J1",
    "msg": "human-readable explanation",
    "data": {}
  }]
}
```

`robot.status` is one of `idle`, `moving`, `waiting`, `picking`, `dropping`, `yielding`, `failed`. Job state is one of `Waiting`, `Assigned`, `PickedUp`, `Stranded`, `Delivered`, `Blocked`. Event objects always contain `id`, `tick`, `type`, `robot`, `job`, `msg`, and `data`.

`planner_rejections` counts search states rejected by vertex or edge reservations during assignment, replanning, and recovery. `conflicts_prevented` counts runtime `CONFLICT_AVOIDED` waits when another robot occupies the next cell; it does not include planner rejections. The sparse congestion heatmap counts moving-robot occupancy and job-related wait ticks, excluding idle/parked robots.

## Scheduling rules

Ticks apply queued commands, assign waiting work, replan missing/invalid routes, check conflicts/deadlock, advance one robot action, update metrics/events, then expose the snapshot. Jobs transition `Waiting -> Assigned -> PickedUp -> Delivered`. Failed pre-pickup work returns to `Waiting`; failed carrying work becomes `Stranded` and is eligible for recovery. Delivered jobs are immutable.

Space-time A* searches `(x, y, t)` with Manhattan heuristic and 4 moves plus wait, bounded to 60 ticks. Reservations include vertices and directed edges, preventing vertex collisions and swaps; goal cells are reserved one extra tick and idle robots park in place. Waiting jobs use nearest reachable idle robot, with robot ID as tie-breaker. Route planning prioritizes carrying jobs, then job ID, then robot ID.

Blocking an occupied cell returns `CELL_OCCUPIED`. Other affected routes are released and replanned. Deadlock detection checks stalls over six ticks before wait-for cycles; a victim may yield to a pull-out and back off with deterministic seeded timing.

## Scenario format

```json
{
  "id": "scenario_id",
  "name": "Scenario name",
  "description": "What this scenario demonstrates",
  "seed": 17,
  "grid": {"width": 12, "height": 7, "obstacles": [], "blocked": [], "pickups": [], "drops": []},
  "robots": [{"id": "R1", "start": [0, 0]}],
  "jobs": [{"pickup_id": "P1", "drop_id": "D1", "at_tick": 0}],
  "scripted_events": [{"tick": 4, "action": "fail_robot", "robot": "R1"}]
}
```

Events use the exact types `JOB_CREATED`, `JOB_ASSIGNED`, `JOB_WAITING`, `PATH_PLANNED`, `WAIT`, `CONFLICT_AVOIDED`, `DEADLOCK_DETECTED`, `DEADLOCK_RESOLVED`, `PICKUP`, `DELIVERED`, `ROBOT_FAILED`, `JOB_REASSIGNED`, `PACKAGE_STRANDED`, `CELL_BLOCKED`, `CELL_UNBLOCKED`, `REPLAN`, `JOB_UNREACHABLE`, and `INVARIANT_VIOLATION`. `JOB_WAITING` is emitted once when no idle robot is available; `JOB_UNREACHABLE` is reserved for jobs with no feasible path.
