from __future__ import annotations

from dataclasses import dataclass, field

Position = tuple[int, int]
TimedPosition = tuple[int, int, int]


@dataclass
class Grid:
    width: int
    height: int
    obstacles: set[Position] = field(default_factory=set)
    blocked: set[Position] = field(default_factory=set)
    pickups: dict[str, Position] = field(default_factory=dict)
    drops: dict[str, Position] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "Grid":
        return cls(
            width=int(data["width"]),
            height=int(data["height"]),
            obstacles={tuple(p) for p in data.get("obstacles", [])},
            blocked={tuple(p) for p in data.get("blocked", [])},
            pickups={item["id"]: tuple(item["pos"]) for item in data.get("pickups", [])},
            drops={item["id"]: tuple(item["pos"]) for item in data.get("drops", [])},
        )

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "obstacles": [list(p) for p in sorted(self.obstacles)],
            "blocked": [list(p) for p in sorted(self.blocked)],
            "pickups": [{"id": key, "pos": list(pos)} for key, pos in sorted(self.pickups.items())],
            "drops": [{"id": key, "pos": list(pos)} for key, pos in sorted(self.drops.items())],
        }


@dataclass
class Robot:
    id: str
    pos: Position
    status: str = "idle"
    carrying: str | None = None
    job_id: str | None = None
    path: list[TimedPosition] = field(default_factory=list)
    wait_ticks: int = 0
    stalled_attempts: int = 0
    backoff: int = 0
    yield_goal: Position | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pos": list(self.pos),
            "status": self.status,
            "carrying": self.carrying,
            "job_id": self.job_id,
            "path": [list(step) for step in self.path],
            "wait_ticks": self.wait_ticks,
        }


@dataclass
class Job:
    id: str
    pickup_id: str
    drop_id: str
    state: str = "Waiting"
    owner: str | None = None
    created_tick: int = 0
    assigned_tick: int | None = None
    picked_tick: int | None = None
    delivered_tick: int | None = None
    history: list[str] = field(default_factory=lambda: ["Waiting"])
    stranded_pos: Position | None = None
    original_drop_id: str | None = None
    unreachable_logged: bool = False
    waiting_logged: bool = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pickup_id": self.pickup_id,
            "drop_id": self.drop_id,
            "state": self.state,
            "owner": self.owner,
            "created_tick": self.created_tick,
            "assigned_tick": self.assigned_tick,
            "picked_tick": self.picked_tick,
            "delivered_tick": self.delivered_tick,
            "history": list(self.history),
        }


@dataclass
class Event:
    id: int
    tick: int
    type: str
    robot: str | None
    job: str | None
    msg: str
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tick": self.tick,
            "type": self.type,
            "robot": self.robot,
            "job": self.job,
            "msg": self.msg,
            "data": dict(self.data),
        }


@dataclass
class Metrics:
    planner_rejections: int = 0
    conflicts_prevented: int = 0
    invariant_violations: int = 0
    deadlocks_resolved: int = 0
    reassignments: int = 0
    total_wait_ticks: int = 0
    congestion_samples: list[float] = field(default_factory=list)
    heatmap: dict[Position, int] = field(default_factory=dict)

    def to_dict(self, jobs: list[Job], grid: Grid, occupied: set[Position]) -> dict:
        completed = sum(job.state == "Delivered" for job in jobs)
        total_jobs = len(jobs)
        index = sum(self.congestion_samples[-20:]) / len(self.congestion_samples[-20:]) if self.congestion_samples else 0.0
        heat = [[x, y, count] for (x, y), count in sorted(self.heatmap.items()) if count]
        return {
            "completed_jobs": completed,
            "total_jobs": total_jobs,
            "total_wait_ticks": self.total_wait_ticks,
            "avg_wait_ticks_per_job": self.total_wait_ticks / completed if completed else None,
            "congestion": {"index": round(min(1.0, index), 4), "heatmap": heat},
            "planner_rejections": self.planner_rejections,
            "conflicts_prevented": self.conflicts_prevented,
            "invariant_violations": self.invariant_violations,
            "deadlocks_resolved": self.deadlocks_resolved,
            "reassignments": self.reassignments,
        }
