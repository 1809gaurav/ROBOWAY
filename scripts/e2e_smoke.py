#!/usr/bin/env python3
"""REST/WebSocket smoke checks against a running ROBOWAY backend."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
import websockets

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ("narrow_passage", "failed_robot", "blocked_aisle")
CONTRACT_KEYS = {
    "tick", "status", "speed", "scenario_id", "grid", "robots", "jobs",
    "reservations_count", "deadlock", "metrics", "events_tail",
}


class SmokeFailure(AssertionError):
    pass


class Runner:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.session = requests.Session()
        self.checks: list[tuple[str, bool, str]] = []

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        response = self.session.request(method, f"{self.base}{path}", timeout=5, **kwargs)
        return response

    def expect(self, condition: bool, message: str) -> None:
        if not condition:
            raise SmokeFailure(message)

    def check(self, name: str, callback) -> Any:
        try:
            result = callback()
            self.checks.append((name, True, ""))
            return result
        except Exception as exc:
            self.checks.append((name, False, str(exc)))
            return None

    def health_and_contract(self) -> None:
        for path in ("/health", "/api/state", "/api/scenarios", "/api/ml/status"):
            response = self.request("GET", path)
            self.expect(response.ok, f"GET {path} returned {response.status_code}")
        state = self.request("GET", "/api/state").json()
        self.expect(CONTRACT_KEYS.issubset(state), f"state misses {sorted(CONTRACT_KEYS - set(state))}")
        self.expect("enabled" in self.request("GET", "/api/ml/status").json(), "ML status has no enabled field")
        scenarios = self.request("GET", "/api/scenarios").json().get("scenarios", [])
        self.expect({item["id"] for item in scenarios} == set(SCENARIOS), "scenario list is incomplete")

    def apply_scripted_event(self, event: dict[str, Any]) -> None:
        action = event["action"]
        if action == "fail_robot":
            response = self.request("POST", f"/api/robots/{event['robot']}/fail")
        elif action == "block_cell":
            response = self.request("POST", "/api/cells/block", json={"x": event["x"], "y": event["y"]})
        elif action == "unblock_cell":
            response = self.request("POST", "/api/cells/unblock", json={"x": event["x"], "y": event["y"]})
        else:
            raise SmokeFailure(f"unsupported scenario action: {action}")
        self.expect(response.ok, f"scripted {action} failed: {response.text}")

    def assert_single_owner(self, snapshot: dict[str, Any]) -> None:
        for job in snapshot["jobs"]:
            owners = {job["owner"]} if job.get("owner") else set()
            owners.update(robot["id"] for robot in snapshot["robots"] if robot.get("job_id") == job["id"])
            self.expect(len(owners) <= 1, f"{job['id']} appears owned by {sorted(owners)}")

    def run_scenario(self, scenario_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        scenario_file = ROOT / "scenarios" / f"{scenario_id}.json"
        scenario = json.loads(scenario_file.read_text(encoding="utf-8"))
        response = self.request("POST", f"/api/scenarios/{scenario_id}/load")
        self.expect(response.ok, f"could not load {scenario_id}: {response.text}")
        scripted = {item["tick"]: item for item in scenario.get("scripted_events", [])}
        applied: set[int] = set()
        state = self.request("GET", "/api/state").json()
        last_tick = state["tick"]
        snapshots = [state]
        for _ in range(400):
            current_tick = state["tick"]
            applied_event = False
            if current_tick in scripted and current_tick not in applied:
                self.apply_scripted_event(scripted[current_tick])
                applied.add(current_tick)
                applied_event = True
            # Scenario scripts must be exercised even if the jobs finish early.
            if all(job["state"] == "Delivered" for job in state["jobs"]) and len(applied) == len(scripted) and not applied_event:
                break
            stepped = self.request("POST", "/api/sim/step")
            self.expect(stepped.ok, f"step failed: {stepped.text}")
            state = self.request("GET", "/api/state").json()
            self.expect(state["tick"] >= last_tick, f"tick decreased in {scenario_id}")
            last_tick = state["tick"]
            self.assert_single_owner(state)
            snapshots.append(state)
        else:
            raise SmokeFailure(f"{scenario_id} exceeded 400 ticks")

        self.expect(all(job["state"] == "Delivered" for job in state["jobs"]), f"{scenario_id} did not deliver all jobs")
        self.expect(state["metrics"]["invariant_violations"] == 0, f"{scenario_id} invariant violations: {state['metrics']['invariant_violations']}")
        events = self.request("GET", "/api/events?since=0").json()["events"]
        for job in state["jobs"]:
            delivered = [event for event in events if event["type"] == "DELIVERED" and event["job"] == job["id"]]
            self.expect(len(delivered) == 1, f"{scenario_id}/{job['id']} has {len(delivered)} DELIVERED events")
        return snapshots, events

    def scenario_assertions(self, scenario_id: str, events: list[dict[str, Any]]) -> None:
        types = [event["type"] for event in events]
        if scenario_id == "narrow_passage":
            detected = types.index("DEADLOCK_DETECTED") if "DEADLOCK_DETECTED" in types else -1
            resolved = types.index("DEADLOCK_RESOLVED") if "DEADLOCK_RESOLVED" in types else -1
            self.expect(0 <= detected < resolved, "deadlock detection did not precede resolution")
        elif scenario_id == "failed_robot":
            stranded = next((event for event in events if event["type"] == "PACKAGE_STRANDED"), None)
            self.expect(stranded is not None, "no PACKAGE_STRANDED event")
            recovered = next((event for event in events if event["type"] == "PICKUP" and event["job"] == stranded["job"] and event["robot"] != stranded["robot"]), None)
            self.expect(recovered is not None, "stranded package was not picked up by another robot")
        else:
            blocked = next((index for index, event in enumerate(events) if event["type"] == "CELL_BLOCKED"), -1)
            self.expect(blocked >= 0, "no CELL_BLOCKED event")
            self.expect(any(event["type"] == "REPLAN" for event in events[blocked + 1:]), "no REPLAN after CELL_BLOCKED")

    def command_workflow(self) -> None:
        loaded = self.request("POST", "/api/scenarios/narrow_passage/load")
        self.expect(loaded.ok, "cannot load narrow_passage")
        self.expect(self.request("POST", "/api/sim/start").ok, "start failed")
        added_response = self.request("POST", "/api/jobs", json={"pickup_id": "P3", "drop_id": "D3"})
        self.expect(added_response.ok, f"add-job failed: {added_response.text}")
        added_id = added_response.json()["job_id"]
        state = self.request("GET", "/api/state").json()
        self.expect(any(job["id"] == added_id for job in state["jobs"]), "new job missing from state")
        self.request("POST", "/api/sim/pause")
        candidate = next(job for job in self.request("GET", "/api/state").json()["jobs"] if job["id"] == added_id)
        before = self.request("GET", "/api/state").json()
        validation = self.request("POST", "/api/jobs/validate", json={
            "job_id": candidate["id"], "pickup_id": candidate["pickup_id"], "drop_id": candidate["drop_id"],
        })
        self.expect(validation.ok, f"validation failed: {validation.text}")
        self.expect(before == self.request("GET", "/api/state").json(), "validation mutated state")
        self.request("POST", "/api/sim/start")
        assigned = False
        for _ in range(40):
            if not self.request("POST", "/api/sim/step").ok:
                raise SmokeFailure("step failed during add-job workflow")
            state = self.request("GET", "/api/state").json()
            if next(job for job in state["jobs"] if job["id"] == added_id)["state"] in ("Assigned", "PickedUp", "Delivered"):
                assigned = True
                break
        self.expect(assigned, "added job was not eventually assigned")
        self.request("POST", "/api/sim/pause")

        picked = next((job for job in state["jobs"] if job["state"] == "PickedUp"), None)
        if picked is None:
            for _ in range(30):
                self.request("POST", "/api/sim/step")
                state = self.request("GET", "/api/state").json()
                picked = next((job for job in state["jobs"] if job["state"] == "PickedUp"), None)
                if picked:
                    break
        self.expect(picked is not None, "no PickedUp job available for locked-edit check")
        self.request("POST", "/api/sim/pause")
        edit = self.request("PATCH", f"/api/jobs/{picked['id']}", json={
            "pickup_id": picked["pickup_id"], "drop_id": picked["drop_id"],
        })
        self.expect(edit.status_code == 400 and edit.json().get("error") == "JOB_LOCKED", "PATCH of PickedUp job did not return JOB_LOCKED")

        self.request("POST", "/api/scenarios/narrow_passage/load")
        state = self.request("GET", "/api/state").json()
        x, y = state["robots"][0]["pos"]
        occupied = self.request("POST", "/api/cells/block", json={"x": x, "y": y})
        self.expect(occupied.status_code == 400 and occupied.json().get("error") == "CELL_OCCUPIED", "occupied cell did not return CELL_OCCUPIED")

    async def websocket_workflow(self) -> None:
        parsed = urlparse(self.base)
        ws_scheme = "wss" if parsed.scheme == "https" else "ws"
        ws_url = f"{ws_scheme}://{parsed.netloc}/ws"
        async with websockets.connect(ws_url, open_timeout=5) as websocket:
            initial = json.loads(await asyncio.wait_for(websocket.recv(), 2))
            self.expect(initial.get("type") == "state", "first WebSocket message was not state")
            await asyncio.to_thread(self.request, "POST", "/api/sim/step")
            next_state = json.loads(await asyncio.wait_for(websocket.recv(), 2))
            self.expect(next_state.get("type") == "state", "step did not broadcast a state message")
            await asyncio.to_thread(self.request, "POST", "/api/jobs", json={"pickup_id": "P1", "drop_id": "D1"})
            found_event = False
            for _ in range(4):
                message = json.loads(await asyncio.wait_for(websocket.recv(), 2))
                if message.get("type") == "event":
                    found_event = True
                    break
            self.expect(found_event, "event message did not arrive after job command")

    def print_table(self) -> None:
        width = max((len(name) for name, _, _ in self.checks), default=8)
        print(f"\n{'CHECK':<{width}}  RESULT  DETAILS")
        print(f"{'-' * width}  ------  -------")
        for name, passed, details in self.checks:
            print(f"{name:<{width}}  {'PASS' if passed else 'FAIL':<6}  {details}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8000")
    args = parser.parse_args()
    runner = Runner(args.api)
    runner.check("health + API contract", runner.health_and_contract)
    runs: dict[str, tuple[list[dict[str, Any]], list[dict[str, Any]]]] = {}
    for scenario_id in SCENARIOS:
        result = runner.check(f"{scenario_id} delivery + invariants", lambda sid=scenario_id: runner.run_scenario(sid))
        if result is not None:
            runs[scenario_id] = result
            runner.check(f"{scenario_id} event assertions", lambda sid=scenario_id, events=result[1]: runner.scenario_assertions(sid, events))
    for scenario_id in SCENARIOS:
        if scenario_id not in runs:
            continue
        second = runner.check(f"{scenario_id} deterministic replay", lambda sid=scenario_id: runner.run_scenario(sid))
        if second is not None:
            runner.check(f"{scenario_id} event log equality", lambda first=runs[scenario_id][1], replay=second[1]: runner.expect(first == replay, "event logs differ between identical runs"))
    runner.check("REST job/cell workflow", runner.command_workflow)
    runner.check("WebSocket state + events", lambda: asyncio.run(runner.websocket_workflow()))
    runner.print_table()
    return 1 if any(not passed for _, passed, _ in runner.checks) else 0


if __name__ == "__main__":
    sys.exit(main())
