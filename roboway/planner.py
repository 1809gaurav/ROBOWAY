from heapq import heappop, heappush

from .grid import is_walkable, neighbours
from .models import Grid, Position, TimedPosition
from .reservation import ReservationTable


def plan(
    grid: Grid,
    table: ReservationTable,
    robot_id: str,
    start: Position,
    goal: Position,
    t0: int,
    horizon: int = 60,
) -> list[TimedPosition] | None:
    if not is_walkable(grid, start) or not is_walkable(grid, goal):
        return None
    initial = (start[0], start[1], t0)
    queue: list[tuple[int, int, TimedPosition]] = []
    heappush(queue, (abs(start[0] - goal[0]) + abs(start[1] - goal[1]), 0, initial))
    came_from: dict[TimedPosition, TimedPosition | None] = {initial: None}
    cost: dict[TimedPosition, int] = {initial: 0}
    while queue:
        _, _, current = heappop(queue)
        x, y, tick = current
        if (x, y) == goal:
            path = []
            node: TimedPosition | None = current
            while node is not None:
                path.append(node)
                node = came_from[node]
            return list(reversed(path))
        if tick >= t0 + horizon:
            continue
        next_tick = tick + 1
        for nxt in neighbours(grid, (x, y)) + [(x, y)]:
            nx, ny = nxt
            state = (nx, ny, next_tick)
            if not table.is_free(nx, ny, next_tick, robot_id):
                table.rejections += 1
                continue
            if not table.edge_free(x, y, nx, ny, next_tick, robot_id):
                table.rejections += 1
                continue
            new_cost = cost[current] + 1
            if state in cost and cost[state] <= new_cost:
                continue
            cost[state] = new_cost
            came_from[state] = current
            heuristic = abs(nx - goal[0]) + abs(ny - goal[1])
            heappush(queue, (new_cost + heuristic, new_cost, state))
    return None
