from __future__ import annotations

import heapq
import itertools
import threading
import time
from copy import deepcopy
from typing import Any


WIDTH, HEIGHT = 18, 12
BLOCKED = {
    (x, y)
    for x in range(3, 15)
    for y in range(2, 4)
} | {
    (x, y)
    for x in range(3, 15)
    for y in range(7, 9)
}


def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def space_time_path(
    start: tuple[int, int],
    goal: tuple[int, int],
    reservations: set[tuple[int, int, int]],
    horizon: int = 72,
) -> list[tuple[int, int]]:
    """Find a shortest route that avoids cell and head-on edge reservations."""
    if start == goal:
        return [start]
    counter = itertools.count()
    queue: list[tuple[int, int, int, int, int, int]] = []
    heapq.heappush(queue, (_heuristic(start, goal), 0, next(counter), start[0], start[1], 0))
    parent: dict[tuple[int, int, int], tuple[int, int, int] | None] = {
        (start[0], start[1], 0): None
    }
    visited: set[tuple[int, int, int]] = set()
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1), (0, 0))
    end: tuple[int, int, int] | None = None

    while queue:
        _, steps, _, x, y, tick = heapq.heappop(queue)
        node = (x, y, tick)
        if node in visited:
            continue
        visited.add(node)
        if (x, y) == goal:
            end = node
            break
        if tick >= horizon:
            continue
        for dx, dy in directions:
            nx, ny, next_tick = x + dx, y + dy, tick + 1
            if not (0 <= nx < WIDTH and 0 <= ny < HEIGHT):
                continue
            if (nx, ny) in BLOCKED:
                continue
            if (nx, ny, next_tick) in reservations:
                continue
            if (nx, ny, tick) in reservations and (dx or dy):
                continue
            next_node = (nx, ny, next_tick)
            if next_node in parent:
                continue
            parent[next_node] = node
            cost = steps + 1
            heapq.heappush(
                queue,
                (cost + _heuristic((nx, ny), goal), cost, next(counter), nx, ny, next_tick),
            )

    if end is None:
        return []
    path: list[tuple[int, int]] = []
    cursor: tuple[int, int, int] | None = end
    while cursor is not None:
        path.append((cursor[0], cursor[1]))
        cursor = parent[cursor]
    return list(reversed(path))


def _robot(robot_id: str, name: str, x: int, y: int, color: str, target: tuple[int, int]) -> dict[str, Any]:
    return {
        "id": robot_id,
        "name": name,
        "x": x,
        "y": y,
        "color": color,
        "status": "moving",
        "target": {"x": target[0], "y": target[1]},
        "path": [],
        "progress": 0,
        "battery": 96,
        "completed": 0,
    }


class Simulation:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self._reset()

    def _reset(self) -> None:
        self.running = False
        self.tick = 0
        self.started_at = time.time()
        self.collisions_avoided = 0
        self.completed_jobs = 0
        self.robots = [
            _robot("rw-01", "Atlas", 1, 1, "#b8f16a", (16, 1)),
            _robot("rw-02", "Nova", 16, 10, "#66d9ce", (1, 10)),
            _robot("rw-03", "Pip", 1, 10, "#f1b85b", (16, 10)),
        ]
        self.jobs = [
            {"id": "JOB-2048", "status": "in progress", "robot": "Atlas", "from": "A-04", "to": "Pack 01"},
            {"id": "JOB-2049", "status": "queued", "robot": "Nova", "from": "C-12", "to": "Dock 02"},
            {"id": "JOB-2050", "status": "queued", "robot": "Pip", "from": "B-07", "to": "Pack 02"},
        ]
        self._plan_routes()

    def _plan_routes(self) -> None:
        reservations: set[tuple[int, int, int]] = set()
        for robot in self.robots:
            start = (robot["x"], robot["y"])
            goal = (robot["target"]["x"], robot["target"]["y"])
            robot["path"] = space_time_path(start, goal, reservations)
            for tick, (x, y) in enumerate(robot["path"]):
                reservations.add((x, y, tick))
            if len(robot["path"]) > 1:
                for tick, (x, y) in enumerate(robot["path"][1:], 1):
                    reservations.add((x, y, tick + 1))

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            uptime = int(time.time() - self.started_at)
            return {
                "running": self.running,
                "tick": self.tick,
                "uptime": uptime,
                "collisionsAvoided": self.collisions_avoided,
                "completedJobs": self.completed_jobs,
                "width": WIDTH,
                "height": HEIGHT,
                "blocked": [{"x": x, "y": y} for x, y in sorted(BLOCKED)],
                "robots": deepcopy(self.robots),
                "jobs": deepcopy(self.jobs),
            }

    def start(self) -> dict[str, Any]:
        with self.lock:
            self.running = True
            return self.snapshot()

    def pause(self) -> dict[str, Any]:
        with self.lock:
            self.running = False
            return self.snapshot()

    def reset(self) -> dict[str, Any]:
        with self.lock:
            self._reset()
            return self.snapshot()

    def step(self) -> dict[str, Any]:
        with self.lock:
            self._advance()
            return self.snapshot()

    def _advance(self) -> None:
        reservations: set[tuple[int, int]] = set()
        for robot in sorted(self.robots, key=lambda item: item["id"]):
            path = robot["path"]
            if robot["progress"] + 1 < len(path):
                next_position = path[robot["progress"] + 1]
                if next_position not in reservations:
                    robot["progress"] += 1
                    robot["x"], robot["y"] = next_position
                    robot["battery"] = max(8, robot["battery"] - 0.018)
                else:
                    self.collisions_avoided += 1
            reservations.add((robot["x"], robot["y"]))
        self.tick += 1
        if all(robot["progress"] + 1 >= len(robot["path"]) for robot in self.robots):
            self.completed_jobs += 1
            robot = self.robots[self.completed_jobs % len(self.robots)]
            target = (1, 1) if robot["target"] != {"x": 1, "y": 1} else (16, 10)
            robot["target"] = {"x": target[0], "y": target[1]}
            robot["path"] = space_time_path(
                (robot["x"], robot["y"]),
                target,
                {(r["x"], r["y"], 0) for r in self.robots if r is not robot},
            )
            robot["progress"] = 0
            robot["completed"] += 1
            self._plan_routes()


simulation = Simulation()
