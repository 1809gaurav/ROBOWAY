from collections import deque

from .models import Grid, Position


def is_walkable(grid: Grid, pos: Position) -> bool:
    x, y = pos
    return 0 <= x < grid.width and 0 <= y < grid.height and pos not in grid.obstacles and pos not in grid.blocked


def neighbours(grid: Grid, pos: Position) -> list[Position]:
    x, y = pos
    candidates = [(x, y - 1), (x - 1, y), (x + 1, y), (x, y + 1)]
    return [point for point in candidates if is_walkable(grid, point)]


def bfs(grid: Grid, start: Position, goals: set[Position] | None = None) -> list[Position]:
    queue = deque([start])
    previous: dict[Position, Position | None] = {start: None}
    found = start if goals is None or start in goals else None
    while queue and found is None:
        current = queue.popleft()
        for nxt in neighbours(grid, current):
            if nxt not in previous:
                previous[nxt] = current
                if goals is not None and nxt in goals:
                    found = nxt
                    break
                queue.append(nxt)
    if found is None:
        return []
    path = []
    current: Position | None = found
    while current is not None:
        path.append(current)
        current = previous[current]
    return list(reversed(path))
