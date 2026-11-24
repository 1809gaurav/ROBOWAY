import argparse
import json
from pathlib import Path

from roboway import Simulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a ROBOWAY warehouse scenario.")
    parser.add_argument("--scenario", default="narrow_passage", choices=["narrow_passage", "failed_robot", "blocked_aisle"])
    parser.add_argument("--ticks", type=int, default=120)
    parser.add_argument("--write-mock", action="store_true", help="write the final state to mock_state.json")
    args = parser.parse_args()
    scenario_path = Path(__file__).parent / "scenarios" / f"{args.scenario}.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    sim = Simulation()
    sim.load_scenario(scenario)
    sim.start()
    applied: set[int] = set()
    for _ in range(max(0, args.ticks)):
        for index, event in enumerate(scenario.get("scripted_events", [])):
            if event["tick"] == sim.tick_count and index not in applied:
                if event["action"] == "fail_robot":
                    sim.fail_robot(event["robot"])
                elif event["action"] == "block_cell":
                    sim.block_cell(event["x"], event["y"])
                elif event["action"] == "unblock_cell":
                    sim.unblock_cell(event["x"], event["y"])
                applied.add(index)
        sim.tick()
        if all(job.state == "Delivered" for job in sim.jobs.values()):
            break
    for event in sim.events_since(0):
        print(f"[{event['tick']:03d}] {event['type']}: {event['msg']}")
    print(json.dumps(sim.snapshot()["metrics"], indent=2))
    if args.write_mock:
        (Path(__file__).parent / "mock_state.json").write_text(json.dumps(sim.snapshot(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
