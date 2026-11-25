#!/usr/bin/env python3
"""Hands-free REST-only scenario player for judges and demos."""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("narrow_passage", "failed_robot", "blocked_aisle")


class Player:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.session = requests.Session()

    def call(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.session.request(method, self.base + path, json=body, timeout=8)
        if not response.ok:
            raise RuntimeError(f"{method} {path} returned {response.status_code}: {response.text}")
        return response.json()

    def state(self) -> dict[str, Any]:
        return self.call("GET", "/api/state")

    def step(self) -> dict[str, Any]:
        self.call("POST", "/api/sim/step")
        return self.state()

    def action(self, event: dict[str, Any]) -> None:
        action = event["action"]
        if action == "fail_robot":
            self.call("POST", f"/api/robots/{event['robot']}/fail")
        elif action == "block_cell":
            self.call("POST", "/api/cells/block", {"x": event["x"], "y": event["y"]})
        elif action == "unblock_cell":
            self.call("POST", "/api/cells/unblock", {"x": event["x"], "y": event["y"]})
        else:
            raise RuntimeError(f"Unknown scripted action: {action}")

    def pause_between(self) -> None:
        self.call("POST", "/api/sim/pause")
        time.sleep(5)

    def play_narrow(self, scenario: dict[str, Any]) -> dict[str, Any]:
        return self.play_with_schedule(scenario, scenario.get("scripted_events", []))

    def play_failed(self, scenario: dict[str, Any]) -> dict[str, Any]:
        # These scenario ticks fail one robot before it is assigned and another
        # after it has started carrying work, matching the authored script.
        return self.play_with_schedule(scenario, scenario.get("scripted_events", []))

    def play_blocked(self, scenario: dict[str, Any]) -> dict[str, Any]:
        state = self.state()
        block_queued = False
        unblock_queued = False
        block_tick = None
        for _ in range(400):
            if not block_queued and state["tick"] >= 3:
                result = self.session.post(self.base + "/api/cells/block", json={"x": 8, "y": 3}, timeout=8)
                if result.ok:
                    block_queued = True
                    block_tick = state["tick"]
                    print(f"Blocked mid-aisle cell (8,3) at simulation tick {block_tick}", flush=True)
                elif result.status_code != 400 or result.json().get("error") != "CELL_OCCUPIED":
                    raise RuntimeError(f"Unable to block aisle: {result.text}")
            active = [job for job in state["jobs"] if job["state"] != "Delivered"]
            if block_queued and not unblock_queued and not active and state["tick"] > (block_tick or 0):
                self.call("POST", "/api/cells/unblock", {"x": 8, "y": 3})
                unblock_queued = True
                state = self.step()
                continue
            if all(job["state"] == "Delivered" for job in state["jobs"]) and block_queued and unblock_queued:
                break
            state = self.step()
        else:
            raise RuntimeError("blocked_aisle exceeded 400 ticks")
        if block_queued and not unblock_queued:
            self.call("POST", "/api/cells/unblock", {"x": 8, "y": 3})
            state = self.step()
        return state

    def play_with_schedule(self, scenario: dict[str, Any], schedule: list[dict[str, Any]]) -> dict[str, Any]:
        actions_by_tick = {item["tick"]: item for item in schedule}
        applied: set[int] = set()
        state = self.state()
        for _ in range(400):
            if state["tick"] in actions_by_tick and state["tick"] not in applied:
                event = actions_by_tick[state["tick"]]
                self.action(event)
                applied.add(state["tick"])
                print(f"{scenario['id']}: {event['action']} at tick {state['tick']}", flush=True)
            if all(job["state"] == "Delivered" for job in state["jobs"]) and len(applied) == len(actions_by_tick):
                return state
            state = self.step()
        raise RuntimeError(f"{scenario['id']} exceeded 400 ticks")

    def play_once(self) -> None:
        summary = []
        for scenario_id in SCENARIOS:
            scenario = json.loads((ROOT / "scenarios" / f"{scenario_id}.json").read_text(encoding="utf-8"))
            self.call("POST", f"/api/scenarios/{scenario_id}/load")
            self.call("POST", "/api/sim/start")
            if scenario_id == "narrow_passage":
                final = self.play_narrow(scenario)
            elif scenario_id == "failed_robot":
                final = self.play_failed(scenario)
            else:
                final = self.play_blocked(scenario)
            if not all(job["state"] == "Delivered" for job in final["jobs"]):
                raise RuntimeError(f"{scenario_id} ended before all jobs were delivered")
            metrics = final["metrics"]
            summary.append((
                scenario_id,
                f"{metrics['completed_jobs']}/{metrics['total_jobs']}",
                metrics["deadlocks_resolved"],
                metrics["reassignments"],
                metrics["invariant_violations"],
            ))
            self.pause_between()
        print("\nScenario            Delivered  Deadlocks  Reassignments  Invariant violations")
        print("------------------  ---------  ---------  -------------  --------------------")
        for row in summary:
            print(f"{row[0]:<18}  {row[1]:<9}  {row[2]:<9}  {row[3]:<13}  {row[4]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--loop", action="store_true")
    args = parser.parse_args()
    player = Player(args.api)

    def pause_simulation(_signum=None, _frame=None):
        try:
            player.call("POST", "/api/sim/pause")
            print("\nDemo stopped; simulation paused.", flush=True)
        except requests.RequestException as exc:
            print(f"\nDemo stopped; pause request failed: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, pause_simulation)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, pause_simulation)
    try:
        while True:
            player.play_once()
            if not args.loop:
                break
        return 0
    except Exception as exc:
        print(f"Demo player failed: {exc}", file=sys.stderr)
        try:
            player.call("POST", "/api/sim/pause")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
