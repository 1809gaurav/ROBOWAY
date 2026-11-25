from collections import defaultdict
from random import Random

from .grid import bfs, is_walkable
from .models import Grid, Job, Robot


def wait_for_graph(robots: list[Robot], owner_at: dict[tuple[int, int], str]) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for robot in robots:
        if robot.status != "waiting" or robot.wait_ticks <= 1 or len(robot.path) < 2:
            continue
        target = robot.path[1][:2]
        owner = owner_at.get(target)
        if owner and owner != robot.id:
            graph[robot.id].add(owner)
    return graph


def find_cycle(graph: dict[str, set[str]]) -> list[str]:
    visiting: list[str] = []
    visited: set[str] = set()

    def visit(node: str) -> list[str]:
        if node in visiting:
            return visiting[visiting.index(node):] + [node]
        if node in visited:
            return []
        visiting.append(node)
        for nxt in sorted(graph.get(node, set())):
            found = visit(nxt)
            if found:
                return found
        visiting.pop()
        visited.add(node)
        return []

    for node in sorted(graph):
        found = visit(node)
        if found:
            return found
    return []


def choose_pullout(grid: Grid, robot: Robot, others: list[Robot], corridor: set[tuple[int, int]]) -> tuple[int, int] | None:
    occupied = {other.pos for other in others if other.id != robot.id and other.status != "failed"}
    candidates = {
        (x, y)
        for x in range(grid.width)
        for y in range(grid.height)
        if is_walkable(grid, (x, y))
        and (x, y) not in corridor
        and (x, y) not in occupied
        and (x, y) != robot.pos
        and (x, y)[1] != robot.pos[1]
    }
    route = bfs(grid, robot.pos, candidates)
    return route[-1] if route else None


def backoff_ticks(seed: int, robot_id: str, attempt: int) -> int:
    return Random(f"{seed}:{robot_id}:{attempt}").randint(2, 5)


def job_victim_priority(robot: Robot, jobs: dict[str, Job]) -> tuple[int, int, str]:
    job = jobs.get(robot.job_id or "")
    return (1 if robot.carrying else 0, -(job.created_tick if job else 0), robot.id)
