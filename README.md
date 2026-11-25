# ROBOWAY simulation core

Pure-Python, deterministic, tick-based engine for coordinating robots on a warehouse grid. Requires Python 3.11+ and has no runtime dependencies.

## Run

```powershell
python -m pytest
python run_demo.py --scenario narrow_passage --ticks 120
```

Choose `narrow_passage`, `failed_robot`, or `blocked_aisle`. The demo prints the event history and final metrics. Add `--write-mock` to write the final snapshot to `mock_state.json`.

## Judge terminal demo

```powershell
python demo_cli.py
python demo_cli.py --scenario narrow_passage --scripted
python demo_cli.py --scenario narrow_passage --scripted --no-ui
```

The interactive view redraws the warehouse, job table, metrics, and recent events. Use `1`/`2`/`3` to change scenarios, `SPACE` to pause/resume, `+`/`-` to adjust playback speed, and `n` to single-step while paused. `a`, `f`, `b`, and `u` add a job, fail a robot, block a cell, and unblock a cell; `r` restarts, `e` exports `demo_events.json`, and `q` quits. The scripted no-UI mode prints the events, final metrics, and run summary.

## Running the server

From the repository root in Windows PowerShell, install the server dependencies and start with either command:

```powershell
python -m pip install -r requirements.txt
python run_server.py --host 0.0.0.0 --port 8000
# Or run Uvicorn directly:
python -m uvicorn roboway.server:app --host 0.0.0.0 --port 8000
```

PowerShell examples use `curl.exe` to avoid the legacy `curl` alias:

```powershell
curl.exe -X POST http://localhost:8000/api/scenarios/narrow_passage/load
curl.exe -X POST http://localhost:8000/api/sim/start
curl.exe -X POST http://localhost:8000/api/jobs -H "Content-Type: application/json" -d '{"pickup_id":"P1","drop_id":"D1"}'
curl.exe -X POST http://localhost:8000/api/cells/block -H "Content-Type: application/json" -d '{"x":8,"y":3}'
curl.exe -X POST http://localhost:8000/api/robots/R1/fail
```

The REST endpoints are under `/api`; `/ws` streams state and event messages. The Vite origins on port 5173 are allowed by default. Add other comma-separated origins in `ROBOWAY_CORS_ORIGINS`.

## Use

```python
import json
from roboway import Simulation

scenario = json.load(open("scenarios/narrow_passage.json", encoding="utf-8"))
sim = Simulation()
sim.load_scenario(scenario)
sim.start()
sim.tick()
state = sim.snapshot()
```

See [docs/CONTRACT.md](docs/CONTRACT.md) for facade methods, scenario inputs, event types, and the snapshot schema.

Metrics distinguish `planner_rejections` (search states rejected by reservations) from `conflicts_prevented` (runtime `CONFLICT_AVOIDED` waits caused by an occupied next cell). The congestion heatmap includes moving robots and job-related waits, not idle/parked occupancy.

## Assumptions

- Ticks start at zero; events record the tick in which the operation occurs.
- Scenario jobs become available at their declared `at_tick`.
- Edit suggestions select a currently configured pickup/drop by Manhattan proximity when the requested route is unavailable.
- A stranded package remains recoverable at its failure coordinate; a robot that fails before pickup leaves an obstacle at its cell.

## Run everything

From the repository root:

```powershell
python -m pip install -r requirements.txt
python run_server.py --host 0.0.0.0 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://<laptop-ip>:5173` from a phone on the same network. Use the 3D/2D toggle on `/monitor`, tap a robot or choose one from the robot list to follow it, and use "Stop following" to return to normal controls.

Manual verification checklist:
- Load each of `narrow_passage`, `failed_robot`, and `blocked_aisle`.
- Start the engine, adjust speed, step while paused, and add a job.
- Fail a robot and block/unblock a cell.
- Open the phone monitor, confirm live 3D tracking and WebGL fallback behavior.
- Stop the backend to see the reconnect banner, restart it, and confirm recovery.
