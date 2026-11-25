from .models import Grid, Metrics, Robot
from .reservation import ReservationTable


def update_metrics(metrics: Metrics, grid: Grid, robots: list[Robot], table: ReservationTable, tick: int) -> None:
    occupied = {robot.pos for robot in robots if robot.status != "failed"}
    reserved_cells = {(x, y) for x, y, reserved_tick in table.vertices if reserved_tick == tick}
    walkable = max(1, grid.width * grid.height - len(grid.obstacles) - len(grid.blocked))
    metrics.congestion_samples.append(len(occupied | reserved_cells) / walkable)
    if len(metrics.congestion_samples) > 20:
        metrics.congestion_samples.pop(0)
    for robot in robots:
        if robot.status == "moving":
            metrics.heatmap[robot.pos] = metrics.heatmap.get(robot.pos, 0) + 1
        if robot.job_id and robot.status == "waiting":
            metrics.total_wait_ticks += 1
            metrics.heatmap[robot.pos] = metrics.heatmap.get(robot.pos, 0) + 1
