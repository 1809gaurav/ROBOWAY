from __future__ import annotations

from copy import deepcopy
from random import Random

from .assigner import assignment_order, robot_priority
from .conflicts import find_conflicts
from .deadlock import backoff_ticks, choose_pullout, find_cycle, job_victim_priority, wait_for_graph
from .events import EventLog
from .failures import fail_robot as apply_failure
from .grid import bfs, is_walkable
from .metrics import update_metrics
from .models import Grid, Job, Metrics, Position, Robot, TimedPosition
from .planner import plan
from .reservation import ReservationTable


class Simulation:
    def __init__(self) -> None:
        self.tick_count = 0
        self.status = "paused"
        self.speed = 1.0
        self.scenario_id = ""
        self.seed = 0
        self.grid = Grid(1, 1)
        self.robots: dict[str, Robot] = {}
        self.jobs: dict[str, Job] = {}
        self.reservations = ReservationTable()
        self.metrics = Metrics()
        self.events = EventLog()
        self.deadlock = {"active": False, "cycle": []}
        self._next_job = 1
        self._commands: list[tuple[str, tuple]] = []
        self._delivered_count = 0
        self._scripted_events: list[dict] = []
        self._replan_old_lengths: dict[str, int] = {}
        self._rng = Random(0)

    def load_scenario(self, scenario: dict) -> None:
        self.tick_count = 0
        self.status = "paused"
        self.speed = 1.0
        self.scenario_id = scenario["id"]
        self.seed = int(scenario.get("seed", 0))
        self._rng = Random(self.seed)
        self.grid = Grid.from_dict(scenario["grid"])
        self.robots = {
            item["id"]: Robot(item["id"], tuple(item["start"]))
            for item in scenario.get("robots", [])
        }
        self.jobs = {}
        self.reservations = ReservationTable()
        self.metrics = Metrics()
        self.events = EventLog()
        self.deadlock = {"active": False, "cycle": []}
        self._next_job = 1
        self._commands = []
        self._delivered_count = 0
        self._scripted_events = deepcopy(scenario.get("scripted_events", []))
        self._replan_old_lengths = {}
        for item in scenario.get("jobs", []):
            job_id = self._new_job_id()
            self.jobs[job_id] = Job(job_id, item["pickup_id"], item["drop_id"], created_tick=int(item.get("at_tick", 0)))

    def start(self) -> None:
        self.status = "running"

    def pause(self) -> None:
        self.status = "paused"

    def set_speed(self, speed: float) -> dict | None:
        if speed <= 0:
            return self._error("INVALID_SPEED", "speed must be greater than zero")
        self.speed = float(speed)
        return None

    def _new_job_id(self) -> str:
        existing = set(self.jobs)
        while f"J{self._next_job}" in existing:
            self._next_job += 1
        job_id = f"J{self._next_job}"
        self._next_job += 1
        return job_id

    def add_job(self, pickup_id: str, drop_id: str) -> str:
        job_id = self._new_job_id()
        self.jobs[job_id] = Job(job_id, pickup_id, drop_id, created_tick=self.tick_count)
        self.events.append(self.tick_count, "JOB_CREATED", f"{job_id} created for pickup {pickup_id} and drop {drop_id}", job=job_id)
        return job_id

    def validate_job_edit(self, job_id: str, pickup_id: str, drop_id: str) -> dict:
        job = self.jobs.get(job_id)
        if job is None:
            return self._error("JOB_NOT_FOUND", f"Job {job_id} does not exist")
        if job.state in ("PickedUp", "Delivered"):
            return self._error("JOB_LOCKED", f"Job {job_id} can no longer be edited")
        if pickup_id not in self.grid.pickups or drop_id not in self.grid.drops:
            return self._conflict_suggestion(pickup_id, drop_id, "Unknown pickup or drop")
        table = self._build_reservations(excluding_job=job_id)
        robot = self.robots.get(job.owner or "")
        candidates = [robot] if robot and robot.status != "failed" else [
            item for item in self.robots.values() if item.status == "idle"
        ]
        for candidate in candidates:
            if candidate is None:
                continue
            pickup_path = plan(self.grid, table, candidate.id, candidate.pos, self.grid.pickups[pickup_id], self.tick_count, 60)
            if pickup_path is None:
                continue
            pickup_table = deepcopy(table)
            pickup_table.reserve_path(candidate.id, pickup_path)
            if plan(self.grid, pickup_table, candidate.id, self.grid.pickups[pickup_id], self.grid.drops[drop_id], pickup_path[-1][2], 60):
                return {"ok": True, "result": "valid"}
        return self._conflict_suggestion(pickup_id, drop_id, "No available robot can reach both locations")

    def _conflict_suggestion(self, pickup_id: str, drop_id: str, reason: str) -> dict:
        pickup_options = sorted(
            self.grid.pickups,
            key=lambda key: self._distance_to_location(key, self.grid.pickups),
        )
        drop_options = sorted(
            self.grid.drops,
            key=lambda key: self._distance_to_location(key, self.grid.drops),
        )
        suggestion = {
            "pickup_id": pickup_options[0] if pickup_options else pickup_id,
            "drop_id": drop_options[0] if drop_options else drop_id,
        }
        return {"ok": True, "result": "conflict", "reason": reason, "suggestion": suggestion}

    def _distance_to_location(self, key: str, locations: dict[str, Position]) -> int:
        points = [robot.pos for robot in self.robots.values() if robot.status != "failed"]
        return min((abs(x - locations[key][0]) + abs(y - locations[key][1]) for x, y in points), default=10**9)

    def edit_job(self, job_id: str, pickup_id: str, drop_id: str) -> dict:
        result = self.validate_job_edit(job_id, pickup_id, drop_id)
        if not result.get("ok") or result.get("result") != "valid":
            return result
        job = self.jobs[job_id]
        if job.state == "Delivered":
            return self._error("JOB_LOCKED", f"Delivered job {job_id} cannot be edited")
        job.pickup_id = pickup_id
        job.drop_id = drop_id
        job.owner = None
        job.state = "Waiting"
        job.history.append("Waiting")
        for robot in self.robots.values():
            if robot.job_id == job_id:
                robot.job_id = None
                robot.carrying = None
                robot.status = "idle"
                robot.path.clear()
        self.events.append(self.tick_count, "REPLAN", f"{job_id} edited; route will be replanned", job=job_id)
        return {"ok": True, "result": "valid"}

    def block_cell(self, x: int, y: int) -> dict:
        pos = (x, y)
        if any(robot.pos == pos and robot.status != "failed" for robot in self.robots.values()):
            return self._error("CELL_OCCUPIED", f"Cell {pos} is occupied")
        if not self._in_bounds(pos) or pos in self.grid.obstacles:
            return self._error("INVALID_CELL", f"Cell {pos} cannot be blocked")
        affected = []
        for robot in self.robots.values():
            if any(step[:2] == pos for step in robot.path[1:]):
                affected.append(robot.id)
                self.reservations.release_robot(robot.id)
        self._commands.append(("block", (pos,)))
        return {"ok": True, "affected_robots": sorted(affected)}

    def unblock_cell(self, x: int, y: int) -> dict:
        pos = (x, y)
        if pos not in self.grid.blocked:
            self._commands.append(("unblock", (pos,)))
        else:
            self._commands.append(("unblock", (pos,)))
        return {"ok": True}

    def fail_robot(self, robot_id: str) -> dict:
        robot = self.robots.get(robot_id)
        if robot is None:
            return self._error("ROBOT_NOT_FOUND", f"Robot {robot_id} does not exist")
        if robot.status == "failed":
            return self._error("ROBOT_FAILED", f"Robot {robot_id} has already failed")
        self._commands.append(("fail", (robot_id,)))
        return {"ok": True, "carrying_job": robot.carrying}

    def _in_bounds(self, pos: Position) -> bool:
        return 0 <= pos[0] < self.grid.width and 0 <= pos[1] < self.grid.height

    @staticmethod
    def _error(code: str, message: str) -> dict:
        return {"ok": False, "error": code, "message": message}

    def _apply_commands(self) -> None:
        commands, self._commands = self._commands, []
        for command, args in commands:
            if command == "block":
                pos = args[0]
                self.grid.blocked.add(pos)
                self.events.append(self.tick_count, "CELL_BLOCKED", f"Cell {pos} blocked; affected routes will be replanned", data={"pos": list(pos)})
            elif command == "unblock":
                pos = args[0]
                self.grid.blocked.discard(pos)
                self.events.append(self.tick_count, "CELL_UNBLOCKED", f"Cell {pos} unblocked; blocked jobs will retry", data={"pos": list(pos)})
                for job in self.jobs.values():
                    if job.state == "Blocked":
                        job.state = "Waiting"
                        job.owner = None
                        job.history.append("Waiting")
            elif command == "fail":
                robot_id = args[0]
                robot = self.robots[robot_id]
                job_id, disposition = apply_failure(robot, self.jobs, self.tick_count)
                self.reservations.release_robot(robot_id)
                if disposition == "stranded" and job_id:
                    job = self.jobs[job_id]
                    self.events.append(self.tick_count, "PACKAGE_STRANDED", f"{job_id} stranded at {robot.pos} after {robot_id} failed", robot_id, job_id)
                    self.events.append(self.tick_count, "ROBOT_FAILED", f"ROBOT FAILED: {robot_id} at {robot.pos} carrying {job_id}, package stranded at {robot.pos}", robot_id, job_id)
                else:
                    self.grid.obstacles.add(robot.pos)
                    self.events.append(self.tick_count, "ROBOT_FAILED", f"ROBOT FAILED: {robot_id} at {robot.pos}; cell becomes an obstacle", robot_id, job_id)
                    if disposition == "reassigned" and job_id:
                        self.metrics.reassignments += 1
                        self.events.append(self.tick_count, "JOB_REASSIGNED", f"{job_id} returned to Waiting after {robot_id} failed", robot_id, job_id)

    def _build_reservations(self, excluding_job: str | None = None) -> ReservationTable:
        table = ReservationTable()
        horizon = self.tick_count + 60
        for robot in self.robots.values():
            if robot.status == "failed" or (excluding_job is not None and robot.job_id == excluding_job):
                continue
            if robot.path and robot.path[0][:2] == robot.pos:
                table.reserve_path(robot.id, robot.path)
            elif robot.status == "idle" or (robot.status == "waiting" and robot.job_id is None):
                table.reserve_stationary(robot.id, robot.pos, self.tick_count, horizon)
            else:
                table.reserve_stationary(robot.id, robot.pos, self.tick_count, min(horizon, self.tick_count + 1))
        return table

    def _target_for(self, robot: Robot) -> Position | None:
        if robot.status == "yielding" and robot.yield_goal is not None:
            return robot.yield_goal
        job = self.jobs.get(robot.job_id or "")
        if not job:
            return None
        if job.state == "Stranded" and job.stranded_pos is not None:
            return job.stranded_pos
        if job.state in ("Assigned", "Waiting"):
            return self.grid.pickups.get(job.pickup_id)
        if job.state == "PickedUp":
            return self.grid.drops.get(job.drop_id)
        return None

    def _assign_waiting_jobs(self) -> None:
        table = self._build_reservations()
        for job in sorted(self.jobs.values(), key=lambda item: (item.created_tick, item.id)):
            if job.state != "Stranded" or job.owner is not None or job.stranded_pos is None:
                continue
            reachable = []
            for robot in self.robots.values():
                if robot.status != "idle" or robot.job_id is not None:
                    continue
                candidate_table = deepcopy(table)
                candidate_table.release_robot(robot.id)
                previous_rejections = candidate_table.rejections
                route = plan(self.grid, candidate_table, robot.id, robot.pos, job.stranded_pos, self.tick_count, 60)
                self.metrics.planner_rejections += candidate_table.rejections - previous_rejections
                if route is not None:
                    reachable.append((len(route), robot.id))
            if reachable:
                robot = self.robots[min(reachable)[1]]
                robot.job_id = job.id
                robot.status = "moving"
                job.owner = robot.id
                self.events.append(self.tick_count, "JOB_REASSIGNED", f"{job.id} assigned to {robot.id} to recover the stranded package", robot.id, job.id)
                previous_rejections = table.rejections
                route = plan(self.grid, table, robot.id, robot.pos, job.stranded_pos, self.tick_count, 60)
                self.metrics.planner_rejections += table.rejections - previous_rejections
                if route:
                    table.reserve_path(robot.id, route)
        eligible = [job for job in self.jobs.values() if job.created_tick <= self.tick_count]
        for job in assignment_order(eligible):
            best: tuple[int, str] | None = None
            idle_robots = [
                robot for robot in sorted(self.robots.values(), key=lambda item: item.id)
                if robot.status == "idle" and robot.job_id is None
            ]
            if not idle_robots:
                if not job.waiting_logged:
                    self.events.append(
                        self.tick_count,
                        "JOB_WAITING",
                        f"{job.id} is waiting: no idle robot available",
                        job=job.id,
                    )
                    job.waiting_logged = True
                continue
            for robot in idle_robots:
                goal = self.grid.pickups.get(job.pickup_id)
                if goal is None:
                    continue
                candidate_table = deepcopy(table)
                candidate_table.release_robot(robot.id)
                previous_rejections = candidate_table.rejections
                route = plan(self.grid, candidate_table, robot.id, robot.pos, goal, self.tick_count, 60)
                self.metrics.planner_rejections += candidate_table.rejections - previous_rejections
                if route is None:
                    continue
                candidate = (len(route), robot.id)
                if best is None or candidate < best:
                    best = candidate
            if best is None:
                if not job.unreachable_logged:
                    self.events.append(
                        self.tick_count,
                        "JOB_UNREACHABLE",
                        f"{job.id} is unreachable: no path exists to pickup {job.pickup_id}",
                        job=job.id,
                    )
                    job.unreachable_logged = True
                continue
            robot = self.robots[best[1]]
            robot.job_id = job.id
            robot.status = "moving"
            job.owner = robot.id
            job.state = "Assigned"
            job.assigned_tick = self.tick_count
            job.history.append(f"Assigned:{robot.id}")
            self.events.append(self.tick_count, "JOB_ASSIGNED", f"{job.id} assigned to {robot.id}; nearest reachable route selected", robot.id, job.id)
            table.release_robot(robot.id)
            previous_rejections = table.rejections
            route = plan(self.grid, table, robot.id, robot.pos, self.grid.pickups[job.pickup_id], self.tick_count, 60)
            self.metrics.planner_rejections += table.rejections - previous_rejections
            if route:
                table.reserve_path(robot.id, route)

    def _replan(self) -> None:
        table = self._build_reservations()
        ordered = sorted(
            (robot for robot in self.robots.values() if robot.status != "failed"),
            key=lambda robot: (0 if robot.status == "yielding" else 1, robot_priority(robot, self.jobs)),
        )
        for robot in ordered:
            target = self._target_for(robot)
            if target is None:
                if robot.status not in ("yielding", "failed"):
                    robot.status = "idle"
                    robot.path.clear()
                continue
            valid = bool(
                robot.path
                and robot.path[0][:2] == robot.pos
                and (len(robot.path) == 1 or robot.path[1][2] == self.tick_count + 1)
            )
            if valid:
                valid = all(is_walkable(self.grid, step[:2]) for step in robot.path[1:])
            if valid and len(robot.path) > 1:
                next_pos = robot.path[1][:2]
                valid = not any(
                    other.id != robot.id
                    and other.pos == next_pos
                    and other.status == "idle"
                    for other in self.robots.values()
                )
            if valid:
                continue
            old_path = list(robot.path)
            cached_old_steps = self._replan_old_lengths.pop(robot.id, None)
            had_old_path = bool(old_path) or cached_old_steps is not None
            old_steps = cached_old_steps if cached_old_steps is not None else max(0, len(old_path) - 1)
            table.release_robot(robot.id)
            previous_rejections = table.rejections
            route = plan(self.grid, table, robot.id, robot.pos, target, self.tick_count, 60)
            self.metrics.planner_rejections += table.rejections - previous_rejections
            if route is None:
                job = self.jobs.get(robot.job_id or "")
                if job and job.state not in ("PickedUp", "Stranded"):
                    job.state = "Blocked"
                    job.owner = None
                    job.history.append("Blocked")
                    robot.job_id = None
                    robot.status = "idle"
                    self.events.append(self.tick_count, "JOB_UNREACHABLE", f"{job.id} is Blocked because no route to {target} exists", robot.id, job.id)
                robot.path.clear()
                continue
            same_path = bool(old_path) and [step[:2] for step in old_path] == [step[:2] for step in route]
            robot.path = route
            robot.status = "yielding" if robot.yield_goal else "moving"
            table.reserve_path(robot.id, route)
            new_steps = max(0, len(route) - 1)
            if new_steps and not same_path:
                if had_old_path:
                    old_description = str(old_steps) if old_steps else "at goal"
                    event_type = "REPLAN"
                    message = f"{robot.id} re-planned: new path {new_steps} steps (was {old_description})"
                else:
                    event_type = "PATH_PLANNED"
                    message = f"{robot.id} planned: new path {new_steps} steps"
                self.events.append(
                    self.tick_count,
                    event_type,
                    message,
                    robot.id,
                    robot.job_id,
                    {"path": [list(step) for step in route]},
                )

    def _handle_deadlocks(self) -> None:
        if self.deadlock["active"] and any(
            robot.status == "yielding" or robot.backoff > 0 for robot in self.robots.values()
        ):
            return
        stalled = [robot for robot in self.robots.values() if robot.status == "waiting" and robot.wait_ticks > 6]
        cycle: list[str] = []
        if stalled:
            cycle = [robot.id for robot in sorted(stalled, key=lambda item: job_victim_priority(item, self.jobs))]
        else:
            owner_at = {
                (x, y): owner
                for (x, y, tick), owner in self.reservations.vertices.items()
                if tick == self.tick_count + 1
            }
            cycle = find_cycle(wait_for_graph(list(self.robots.values()), owner_at))
        if not cycle:
            if self.deadlock["active"] and not any(robot.status == "yielding" for robot in self.robots.values()):
                self.deadlock = {"active": False, "cycle": []}
            return
        involved = {robot_id for robot_id in cycle}
        candidates = [self.robots[robot_id] for robot_id in involved if robot_id in self.robots and self.robots[robot_id].status != "failed"]
        if not candidates:
            return
        victim = sorted(candidates, key=lambda item: job_victim_priority(item, self.jobs))[0]
        cycle_text = " -> ".join(cycle + ([cycle[0]] if cycle and cycle[-1] != cycle[0] else []))
        if stalled:
            reason = f"stall threshold exceeded by {cycle_text or victim.id}"
        else:
            reason = f"wait cycle {cycle_text or victim.id}"
        self.events.append(self.tick_count, "DEADLOCK_DETECTED", f"DEADLOCK DETECTED: {reason}; {victim.id} must yield", victim.id, victim.job_id)
        corridor = {
            step[:2]
            for robot in self.robots.values()
            if robot.status != "failed"
            for step in ([(*robot.pos, self.tick_count)] + robot.path)
        }
        pullout = choose_pullout(self.grid, victim, list(self.robots.values()), corridor)
        if pullout is None:
            victim.stalled_attempts += 1
            if victim.stalled_attempts >= 2 and victim.job_id:
                job = self.jobs[victim.job_id]
                job.state, job.owner = "Waiting", None
                job.history.append("Waiting")
                victim.job_id, victim.carrying = None, None
                victim.status = "idle"
                victim.path.clear()
                self.metrics.reassignments += 1
            self.events.append(self.tick_count, "DEADLOCK_RESOLVED", f"DEADLOCK RESOLVED: {victim.id} backs off; no pull-out was available", victim.id, victim.job_id)
            self.metrics.deadlocks_resolved += 1
            return
        for robot in candidates:
            self._replan_old_lengths.setdefault(robot.id, max(0, len(robot.path) - 1))
            self.reservations.release_robot(robot.id)
            if robot.id != victim.id:
                robot.path.clear()
        victim.yield_goal = pullout
        victim.path.clear()
        victim.status = "yielding"
        victim.stalled_attempts += 1
        victim.backoff = backoff_ticks(self.seed, victim.id, victim.stalled_attempts)
        self.deadlock = {"active": True, "cycle": cycle}
        self.events.append(self.tick_count, "DEADLOCK_RESOLVED", f"DEADLOCK RESOLVED: {victim.id} yields toward pull-out {pullout}", victim.id, victim.job_id)
        self.metrics.deadlocks_resolved += 1

    def _advance_robots(self) -> None:
        for robot in sorted(self.robots.values(), key=lambda item: item.id):
            if robot.status == "failed":
                continue
            if robot.backoff > 0 and robot.status != "yielding":
                robot.backoff -= 1
                robot.status = "waiting"
                continue
            if robot.status == "yielding" and robot.yield_goal == robot.pos:
                robot.yield_goal = None
                robot.status = "waiting"
                robot.path.clear()
                robot.backoff = backoff_ticks(self.seed, robot.id, robot.stalled_attempts)
                if robot.stalled_attempts >= 2 and robot.job_id:
                    job = self.jobs[robot.job_id]
                    if job.state in ("Assigned", "Stranded"):
                        job.state, job.owner = "Waiting", None
                        job.history.append("Waiting")
                        robot.job_id, robot.carrying = None, None
                        robot.status = "idle"
                        self.metrics.reassignments += 1
                continue
            if len(robot.path) > 1:
                next_step = robot.path[1]
                nx, ny, _ = next_step
                if (nx, ny) == robot.pos:
                    robot.path.pop(0)
                    robot.status = "waiting"
                    robot.wait_ticks += 1
                    self.events.append(self.tick_count, "WAIT", f"{robot.id} waits at {robot.pos}: scheduled space-time reservation", robot.id, robot.job_id)
                    continue
                other = next((r for r in self.robots.values() if r.id != robot.id and r.status != "failed" and r.pos == (nx, ny)), None)
                if other:
                    robot.status = "waiting"
                    robot.wait_ticks += 1
                    robot.backoff = max(robot.backoff, 1)
                    self.metrics.conflicts_prevented += 1
                    self.events.append(self.tick_count, "CONFLICT_AVOIDED", f"{robot.id} waits: next cell {(nx, ny)} is occupied by {other.id}", robot.id, robot.job_id)
                    self.events.append(self.tick_count, "WAIT", f"{robot.id} waits at {robot.pos}: cell {(nx, ny)} is occupied by {other.id}", robot.id, robot.job_id)
                    continue
                robot.pos = (nx, ny)
                robot.path.pop(0)
                robot.wait_ticks = 0
                if robot.yield_goal is not None:
                    robot.status = "yielding"
                else:
                    robot.status = "moving"
                continue
            if robot.status == "yielding":
                continue
            job = self.jobs.get(robot.job_id or "")
            if not job:
                robot.status = "idle"
                continue
            if job.state == "Assigned" and robot.pos == self.grid.pickups.get(job.pickup_id):
                job.state = "PickedUp"
                job.owner = robot.id
                job.picked_tick = self.tick_count
                job.history.append(f"PickedUp:{robot.id}")
                robot.carrying = job.id
                robot.status = "picking"
                robot.path.clear()
                self.events.append(self.tick_count, "PICKUP", f"{robot.id} picked up {job.id} at {robot.pos}", robot.id, job.id)
            elif job.state == "Stranded" and robot.pos == job.stranded_pos:
                job.state = "PickedUp"
                job.owner = robot.id
                job.picked_tick = self.tick_count
                job.history.append(f"PickedUp:{robot.id}")
                robot.carrying = job.id
                job.pickup_id = f"RECOVERED:{job.id}"
                robot.status = "picking"
                robot.path.clear()
                self.events.append(self.tick_count, "PICKUP", f"{robot.id} recovered stranded package {job.id} at {robot.pos}", robot.id, job.id)
            elif job.state == "PickedUp" and robot.pos == self.grid.drops.get(job.drop_id):
                job.state = "Delivered"
                job.owner = None
                job.delivered_tick = self.tick_count
                job.history.append("Delivered")
                robot.carrying = None
                robot.job_id = None
                robot.status = "idle"
                robot.path.clear()
                self.events.append(self.tick_count, "DELIVERED", f"{robot.id} delivered {job.id} at {robot.pos}", robot.id, job.id)
            else:
                if robot.status in ("moving", "picking", "dropping"):
                    robot.status = "waiting"
                    robot.wait_ticks += 1
                    self.events.append(self.tick_count, "WAIT", f"{robot.id} waits at {robot.pos}: no next movement action is available", robot.id, robot.job_id)

    def _check_invariants(self, previous_positions: dict[str, Position]) -> None:
        violations = []
        owners: dict[str, int] = {}
        carriers: dict[str, int] = {}
        for job in self.jobs.values():
            if job.owner:
                owners[job.id] = owners.get(job.id, 0) + 1
        for robot in self.robots.values():
            if robot.carrying:
                carriers[robot.carrying] = carriers.get(robot.carrying, 0) + 1
        if any(count > 1 for count in owners.values()) or any(count > 1 for count in carriers.values()):
            violations.append("multiple owners or carriers")
        conflicts = find_conflicts(list(self.robots.values()), previous_positions)
        if conflicts:
            violations.append(str(conflicts))
        delivered = sum(job.state == "Delivered" for job in self.jobs.values())
        if delivered < self._delivered_count:
            violations.append("delivered count decreased")
        self._delivered_count = max(delivered, self._delivered_count)
        for violation in violations:
            self.metrics.invariant_violations += 1
            self.events.append(self.tick_count, "INVARIANT_VIOLATION", f"Invariant violation: {violation}")

    def tick(self) -> None:
        if self.status != "running":
            return
        self._apply_commands()
        self._assign_waiting_jobs()
        self._replan()
        self.reservations = self._build_reservations()
        self._handle_deadlocks()
        previous_positions = {robot.id: robot.pos for robot in self.robots.values()}
        self._advance_robots()
        self.tick_count += 1
        self.reservations = self._build_reservations()
        update_metrics(self.metrics, self.grid, list(self.robots.values()), self.reservations, self.tick_count)
        self._check_invariants(previous_positions)

    def snapshot(self) -> dict:
        return {
            "tick": self.tick_count,
            "status": self.status,
            "speed": self.speed,
            "scenario_id": self.scenario_id,
            "grid": self.grid.to_dict(),
            "robots": [robot.to_dict() for robot in sorted(self.robots.values(), key=lambda item: item.id)],
            "jobs": [job.to_dict() for job in sorted(self.jobs.values(), key=lambda item: item.id)],
            "reservations_count": len(self.reservations),
            "deadlock": deepcopy(self.deadlock),
            "metrics": self.metrics.to_dict(list(self.jobs.values()), self.grid, {r.pos for r in self.robots.values()}),
            "events_tail": [event.to_dict() for event in self.events.events[-50:]],
        }

    def events_since(self, event_id: int) -> list[dict]:
        return self.events.since(event_id)
