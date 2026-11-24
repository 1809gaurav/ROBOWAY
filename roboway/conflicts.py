from .models import Robot


def find_conflicts(
    robots: list[Robot],
    previous_positions: dict[str, tuple[int, int]] | None = None,
) -> list[tuple[str, str, str]]:
    conflicts: list[tuple[str, str, str]] = []
    occupied: dict[tuple[int, int], str] = {}
    for robot in robots:
        if robot.status == "failed":
            continue
        other = occupied.get(robot.pos)
        if other:
            conflicts.append(("vertex", other, robot.id))
        else:
            occupied[robot.pos] = robot.id
    for first in robots:
        if first.status == "failed":
            continue
        for second in robots:
            if first.id >= second.id or second.status == "failed":
                continue
            if previous_positions is not None:
                swapped = (
                    previous_positions.get(first.id) == second.pos
                    and previous_positions.get(second.id) == first.pos
                    and first.pos != previous_positions.get(first.id)
                )
            elif len(first.path) > 1 and len(second.path) > 1:
                swapped = (
                    first.path[0][:2] == first.pos
                    and second.path[0][:2] == second.pos
                    and first.path[1][2] == second.path[1][2]
                    and first.path[0][:2] == second.path[1][:2]
                    and first.path[1][:2] == second.path[0][:2]
                )
            else:
                swapped = False
            if swapped:
                conflicts.append(("swap", first.id, second.id))
    return conflicts
