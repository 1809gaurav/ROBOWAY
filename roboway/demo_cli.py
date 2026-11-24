from __future__ import annotations

import argparse
import json
import os
import select
import shutil
import sys
import time
from pathlib import Path
from typing import TextIO

from .simulation import Simulation

SCENARIOS = ("narrow_passage", "failed_robot", "blocked_aisle")
TICK_LIMIT = 1000
DEFAULT_DELAY = 0.3

COLORS = {
    "reset": "\033[0m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
}

EVENT_COLORS = {
    "DEADLOCK_DETECTED": "magenta",
    "DEADLOCK_RESOLVED": "magenta",
    "ROBOT_FAILED": "red",
    "DELIVERED": "green",
    "WAIT": "yellow",
    "REPLAN": "blue",
    "CELL_BLOCKED": "blue",
}

ROBOT_COLORS = {
    "moving": "green",
    "idle": "green",
    "picking": "green",
    "dropping": "green",
    "waiting": "yellow",
    "yielding": "cyan",
    "failed": "red",
}

def _supports_color(stream: TextIO = sys.stdout) -> bool:
    if not stream.isatty() or os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("TERM", "").lower() == "dumb":
        return False
    if os.name == "nt":
        return any(os.environ.get(key) for key in ("WT_SESSION", "ANSICON", "ConEmuANSI", "TERM"))
    return True


def _paint(text: str, color: str | None, enabled: bool) -> str:
    if not enabled or color is None:
        return text
    return f"{COLORS[color]}{text}{COLORS['reset']}"


def _robot_color(robot: dict, cycle: set[str]) -> str:
    if robot["id"] in cycle:
        return "magenta"
    return ROBOT_COLORS.get(robot["status"], "green")


def _build_grid_lines(state: dict, color: bool) -> list[str]:
    grid = state["grid"]
    width, height = grid["width"], grid["height"]
    locations: dict[tuple[int, int], tuple[str, str | None]] = {}
    for pickup in grid["pickups"]:
        locations[tuple(pickup["pos"])] = (pickup["id"], None)
    for drop in grid["drops"]:
        locations.setdefault(tuple(drop["pos"]), (drop["id"], None))

    cycle = set(state["deadlock"]["cycle"]) if state["deadlock"]["active"] else set()
    robots = {tuple(robot["pos"]): robot for robot in state["robots"]}
    trails: dict[tuple[int, int], tuple[str, str]] = {}
    for robot in state["robots"]:
        if robot["status"] == "failed":
            continue
        robot_color = _robot_color(robot, cycle)
        for step in robot["path"][1:6]:
            point = (step[0], step[1])
            if point not in robots and point not in trails:
                trails[point] = (".", robot_color)

    obstacles = {tuple(point) for point in grid["obstacles"]}
    blocked = {tuple(point) for point in grid["blocked"]}
    tokens = ["#", "X", *(location[0] for location in locations.values())]
    tokens.extend(robot["id"] + ("*" if robot["carrying"] else "") for robot in state["robots"])
    cell_width = max(3, max((len(token) for token in tokens if isinstance(token, str)), default=1))
    border = "+" + "+".join("-" * (cell_width + 2) for _ in range(width)) + "+"
    lines = [border]

    for y in range(height):
        cells = []
        for x in range(width):
            point = (x, y)
            if point in robots:
                robot = robots[point]
                token = robot["id"] + ("*" if robot["carrying"] else "")
                token_color = _robot_color(robot, cycle)
            elif point in obstacles:
                token, token_color = "#", None
            elif point in blocked:
                token, token_color = "X", None
            elif point in locations:
                token, token_color = locations[point]
            elif point in trails:
                token, token_color = trails[point]
            else:
                token, token_color = ".", None
            padded = token.center(cell_width)
            cells.append(" " + _paint(padded, token_color, color) + " ")
        lines.append("|" + "|".join(cells) + "|")
    lines.append(border)
    return lines


def _event_line(event: dict, width: int, color: bool) -> str:
    prefix = f"{event['tick']:>4} {event['type']:<17} "
    available = max(0, width - len(prefix))
    message = event["msg"].replace("\n", " ")
    if len(message) > available:
        message = message[: max(0, available - 3)] + "..."
    return _paint(prefix + message, EVENT_COLORS.get(event["type"]), color)


def render(state: dict, events: list[dict], color: bool | None = None, terminal_width: int | None = None) -> str:
    use_color = _supports_color() if color is None else color
    columns = terminal_width or shutil.get_terminal_size((100, 32)).columns
    grid_lines = _build_grid_lines(state, use_color)
    metrics = state["metrics"]
    deadlock = state["deadlock"]
    right_width = max(32, columns - max(36, state["grid"]["width"] * 6 + 4))

    invariant_color = "green" if metrics["invariant_violations"] == 0 else "red"
    detail_lines = [
        "ROBOWAY | " + state["scenario_id"] + (" | DEADLOCK" if deadlock["active"] else ""),
        f"Tick {state['tick']}  |  Status: {state['status']}",
        f"Completed: {metrics['completed_jobs']}/{metrics['total_jobs']}",
        f"Wait ticks: {metrics['total_wait_ticks']}",
        f"Planner rejections: {metrics['planner_rejections']}",
        f"Conflicts prevented: {metrics['conflicts_prevented']}",
        f"Deadlocks resolved: {metrics['deadlocks_resolved']}",
        f"Reassignments: {metrics['reassignments']}",
        _paint(f"Invariant violations: {metrics['invariant_violations']}", invariant_color, use_color),
        "",
        "JOBS  ID    PICKUP -> DROP      STATE       OWNER",
    ]
    for job in state["jobs"]:
        owner = job["owner"] or "-"
        detail_lines.append(f"      {job['id']:<5} {job['pickup_id']:<7} -> {job['drop_id']:<7} {job['state']:<11} {owner}")
    detail_lines.extend([
        "",
        "Keys: 1/2/3 scenario | SPACE pause | +/- speed | n step",
        "      a add | f fail | b block | u unblock | r restart",
        "      e export events | q quit",
    ])
    if columns >= 84 and state["grid"]["width"] * 6 + 8 < columns:
        left_width = max(len(border) for border in grid_lines) if grid_lines else 0
        lines = []
        for index in range(max(len(grid_lines), len(detail_lines))):
            left = grid_lines[index] if index < len(grid_lines) else ""
            right = detail_lines[index] if index < len(detail_lines) else ""
            lines.append(left.ljust(left_width) + "  " + right)
    else:
        lines = grid_lines + [""] + detail_lines

    lines.extend(["", "EVENTS (latest 10)"])
    for event in events[-10:]:
        lines.append(_event_line(event, columns, use_color))
    return "\n".join(lines)


def _scenario_path(scenario_id: str) -> Path:
    return Path(__file__).resolve().parent.parent / "scenarios" / f"{scenario_id}.json"


def _load_scenario(scenario_id: str) -> dict:
    with _scenario_path(scenario_id).open(encoding="utf-8") as file:
        return json.load(file)


class _KeyReader:
    def __init__(self) -> None:
        self._terminal = None
        self._original = None

    def __enter__(self) -> "_KeyReader":
        if os.name != "nt" and sys.stdin.isatty():
            import termios
            import tty

            self._terminal = termios
            self._original = termios.tcgetattr(sys.stdin.fileno())
            tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, *_: object) -> None:
        self._restore()

    def _restore(self) -> None:
        if self._terminal is not None and self._original is not None:
            self._terminal.tcsetattr(sys.stdin.fileno(), self._terminal.TCSADRAIN, self._original)

    def _enable_raw(self) -> None:
        if self._terminal is not None and self._original is not None:
            import tty

            tty.setcbreak(sys.stdin.fileno())

    def read(self) -> str | None:
        if os.name == "nt":
            import msvcrt

            if not msvcrt.kbhit():
                return None
            key = msvcrt.getwch()
            return key.lower() if key not in ("\x00", "\xe0") else None
        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None
        key = sys.stdin.read(1)
        return key.lower() if key else None

    def prompt(self, message: str) -> str:
        self._restore()
        try:
            return input(message).strip()
        finally:
            self._enable_raw()


class Demo:
    def __init__(self, scenario_id: str, scripted: bool = False) -> None:
        self.scenario_id = scenario_id
        self.scenario = _load_scenario(scenario_id)
        self.scripted = scripted
        self.simulation = Simulation()
        self.simulation.load_scenario(self.scenario)
        self.simulation.start()
        self.paused = False
        self.delay = DEFAULT_DELAY
        self.scripted_index = 0
        self.event_cursor = 0
        self.event_log: list[dict] = []
        self.last_state = self.simulation.snapshot()
        self.notice = ""
        self._collect_events()

    def _collect_events(self) -> list[dict]:
        new_events = self.simulation.events_since(self.event_cursor)
        if new_events:
            self.event_cursor = new_events[-1]["id"]
            self.event_log.extend(new_events)
        return new_events

    def _reset(self, scenario_id: str | None = None) -> None:
        if scenario_id is not None:
            self.scenario_id = scenario_id
        self.scenario = _load_scenario(self.scenario_id)
        self.simulation.load_scenario(self.scenario)
        self.simulation.start()
        self.paused = False
        self.scripted_index = 0
        self.event_cursor = 0
        self.event_log = []
        self.last_state = self.simulation.snapshot()

    def _scripted_commands(self) -> list[str]:
        output = []
        actions = self.scenario.get("scripted_events", [])
        state_tick = self.last_state["tick"]
        while self.scripted_index < len(actions) and actions[self.scripted_index]["tick"] == state_tick:
            action = actions[self.scripted_index]
            name = action["action"]
            if name == "fail_robot":
                result = self.simulation.fail_robot(action["robot"])
                output.append(f"script: fail {action['robot']} -> {result}")
            elif name == "block_cell":
                result = self.simulation.block_cell(action["x"], action["y"])
                output.append(f"script: block ({action['x']}, {action['y']}) -> {result}")
            elif name == "unblock_cell":
                result = self.simulation.unblock_cell(action["x"], action["y"])
                output.append(f"script: unblock ({action['x']}, {action['y']}) -> {result}")
            self.scripted_index += 1
        return output

    def step(self) -> list[dict]:
        if self.scripted:
            for line in self._scripted_commands():
                print(line)
        self.simulation.tick()
        self.last_state = self.simulation.snapshot()
        return self._collect_events()

    def all_delivered(self) -> bool:
        return bool(self.last_state["jobs"]) and all(job["state"] == "Delivered" for job in self.last_state["jobs"])

    def scripts_complete(self) -> bool:
        return self.scripted_index >= len(self.scenario.get("scripted_events", []))

    def export_events(self) -> None:
        all_events = self.simulation.events_since(0)
        with Path("demo_events.json").open("w", encoding="utf-8") as file:
            json.dump(all_events, file, indent=2)
            file.write("\n")

    def summary(self) -> str:
        self._collect_events()
        self.last_state = self.simulation.snapshot()
        metrics = self.last_state["metrics"]
        lines = [
            "",
            "RUN SUMMARY",
            f"Jobs delivered: {metrics['completed_jobs']}/{metrics['total_jobs']}",
        ]
        for job in self.last_state["jobs"]:
            history = " -> ".join(job["history"])
            delivered_by = next(
                (
                    event["robot"]
                    for event in reversed(self.event_log)
                    if event["type"] == "DELIVERED" and event["job"] == job["id"]
                ),
                "-",
            )
            lines.append(
                f"{job['id']} ({job['state']}, owner {job['owner'] or '-'}, "
                f"delivered_by {delivered_by}): {history}"
            )
        lines.append(f"Invariant violations: {metrics['invariant_violations']}")
        lines.append(f"Deadlocks resolved: {metrics['deadlocks_resolved']}")
        return "\n".join(lines)

def _perform_interactive_action(demo: Demo, key: str, reader: _KeyReader) -> bool:
    if key in ("1", "2", "3"):
        demo._reset(SCENARIOS[int(key) - 1])
        demo.notice = f"Loaded {demo.scenario_id}"
    elif key == " ":
        if demo.paused:
            demo.simulation.start()
            demo.notice = "Resumed"
        else:
            demo.simulation.pause()
            demo.notice = "Paused"
        demo.paused = not demo.paused
    elif key == "+" or key == "=":
        demo.delay = max(0.05, demo.delay / 1.25)
        demo.notice = f"Speed: {1 / demo.delay:.1f} ticks/s"
    elif key == "-":
        demo.delay = min(3.0, demo.delay * 1.25)
        demo.notice = f"Speed: {1 / demo.delay:.1f} ticks/s"
    elif key == "n" and demo.paused:
        demo.simulation.start()
        demo.step()
        demo.simulation.pause()
        demo.notice = "Advanced one tick"
    elif key == "a":
        pickup_id = reader.prompt("Pickup id: ")
        drop_id = reader.prompt("Drop id: ")
        demo.notice = f"Added {demo.simulation.add_job(pickup_id, drop_id)}"
        demo._collect_events()
    elif key == "f":
        robot_id = reader.prompt("Robot id: ")
        demo.notice = str(demo.simulation.fail_robot(robot_id))
    elif key == "b":
        try:
            x = int(reader.prompt("Block x: "))
            y = int(reader.prompt("Block y: "))
        except ValueError:
            demo.notice = "Coordinates must be integers."
        else:
            demo.notice = str(demo.simulation.block_cell(x, y))
    elif key == "u":
        try:
            x = int(reader.prompt("Unblock x: "))
            y = int(reader.prompt("Unblock y: "))
        except ValueError:
            demo.notice = "Coordinates must be integers."
        else:
            demo.notice = str(demo.simulation.unblock_cell(x, y))
    elif key == "e":
        demo.export_events()
        demo.notice = "Wrote demo_events.json"
    elif key == "r":
        demo._reset()
        demo.notice = f"Restarted {demo.scenario_id}"
    elif key == "q":
        return False
    return True


def run_interactive(demo: Demo) -> None:
    use_color = _supports_color()
    next_tick = time.monotonic() + demo.delay
    dirty = True
    try:
        with _KeyReader() as reader:
            while True:
                key = reader.read()
                if key is not None:
                    if not _perform_interactive_action(demo, key, reader):
                        break
                    next_tick = time.monotonic() + demo.delay
                    dirty = True
                now = time.monotonic()
                if not demo.paused and now >= next_tick:
                    demo.step()
                    next_tick = now + demo.delay
                    dirty = True
                if dirty:
                    demo.last_state = demo.simulation.snapshot()
                    frame = render(demo.last_state, demo.event_log, use_color)
                    if use_color:
                        sys.stdout.write("\033[2J\033[H")
                    sys.stdout.write(frame + "\n")
                    sys.stdout.write(f"Speed: {1 / demo.delay:.1f} ticks/s  |  {'PAUSED' if demo.paused else 'RUNNING'}\n")
                    if demo.notice:
                        sys.stdout.write(demo.notice + "\n")
                    sys.stdout.flush()
                    dirty = False
                time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    print(demo.summary())


def run_no_ui(demo: Demo) -> None:
    for _ in range(TICK_LIMIT):
        if demo.all_delivered() and (not demo.scripted or demo.scripts_complete()):
            break
        for event in demo.step():
            print(f"[{event['tick']:03d}] {event['type']}: {event['msg']}")
    else:
        print(f"Stopped after {TICK_LIMIT} ticks.")
    demo.last_state = demo.simulation.snapshot()
    print(json.dumps(demo.last_state["metrics"], indent=2))
    print(demo.summary())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Interactive ROBOWAY warehouse simulation demo.")
    parser.add_argument("--scenario", choices=SCENARIOS, default="narrow_passage")
    parser.add_argument("--scripted", action="store_true", help="play the scenario's scripted events")
    parser.add_argument("--no-ui", action="store_true", help="print all events and final metrics without the terminal UI")
    args = parser.parse_args(argv)
    demo = Demo(args.scenario, args.scripted)
    if args.no_ui:
        run_no_ui(demo)
    else:
        run_interactive(demo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
