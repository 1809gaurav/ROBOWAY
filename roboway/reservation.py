from .models import Position, TimedPosition


class ReservationTable:
    def __init__(self) -> None:
        self.vertices: dict[tuple[int, int, int], str] = {}
        self.edges: dict[tuple[int, int, int, int, int], str] = {}
        self.rejections = 0

    def reserve_path(self, robot_id: str, path: list[TimedPosition]) -> None:
        for x, y, tick in path:
            self.vertices[(x, y, tick)] = robot_id
        for first, second in zip(path, path[1:]):
            x1, y1, t1 = first
            x2, y2, _ = second
            self.edges[(x1, y1, x2, y2, t1 + 1)] = robot_id
        if path:
            x, y, tick = path[-1]
            self.vertices[(x, y, tick + 1)] = robot_id

    def reserve_stationary(self, robot_id: str, pos: Position, start: int, horizon: int) -> None:
        x, y = pos
        for tick in range(start, horizon + 1):
            self.vertices[(x, y, tick)] = robot_id

    def release_robot(self, robot_id: str) -> None:
        self.vertices = {key: owner for key, owner in self.vertices.items() if owner != robot_id}
        self.edges = {key: owner for key, owner in self.edges.items() if owner != robot_id}

    def is_free(self, x: int, y: int, tick: int, robot_id: str | None = None) -> bool:
        owner = self.vertices.get((x, y, tick))
        return owner is None or owner == robot_id

    def edge_free(self, x1: int, y1: int, x2: int, y2: int, tick: int, robot_id: str | None = None) -> bool:
        owner = self.edges.get((x2, y2, x1, y1, tick))
        return owner is None or owner == robot_id

    def owner_at(self, x: int, y: int, tick: int) -> str | None:
        return self.vertices.get((x, y, tick))

    def __len__(self) -> int:
        return len(self.vertices)
