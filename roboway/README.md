<<<<<<< HEAD
# RoboWay

RoboWay is an end-to-end warehouse orchestration demo. A FastAPI simulation engine owns the robot positions, jobs, reservations, and time-step state. A React client consumes that state over REST and WebSocket and renders the warehouse in interactive Three.js or a 2D canvas fallback.

## Requirements

- Node.js 20 or newer and npm
- Python 3.10 or newer

## Run locally (Windows PowerShell)

In the project root, install the frontend once:

```powershell
cd frontend
npm install
```

In a second terminal, set up and run the Python API:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

In a third terminal, start the frontend:

```powershell
cd frontend
npm run dev
```

Open <http://localhost:5173>. The API health check is available at <http://localhost:8000/api/health>.

If PowerShell blocks activation, use the environment interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Run checks

```powershell
cd backend
python -m unittest discover -s . -p "test_*.py" -v
cd ..\frontend
npm run build
```

## What is included

- Home, About, Product, Simulator, Fleet Manage, and Profile pages
- FastAPI REST controls for start, pause, reset, and single-step operations
- WebSocket state broadcasts from the authoritative simulation engine
- Space-time A* path planning on an 18 × 12 grid with cell/edge reservations
- Animated 3D warehouse and robot fleet, with orbit controls and planned paths
- 2D canvas fallback with the same robot positions, rack layout, and paths
- Fleet status, active mission queue, battery levels, uptime, simulation tick, and conflict counter

## Phone monitor

Start the backend so it is reachable on your laptop's network interface:

```powershell
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Start the frontend from another terminal with `npm run dev`, then open `http://<laptop-ip>:5173/monitor?api=http://<laptop-ip>:8000` on the phone (for example, replace `<laptop-ip>` with `192.168.1.5`). Use **Monitor on phone** on the simulator page to display a QR code containing this link. The frontend and backend must both be reachable by the phone, and the backend must allow the frontend's network origin through CORS.

Manual phone-monitor checklist:

- [ ] Run the backend with `--host 0.0.0.0` and open `http://<laptop-ip>:5173/monitor?api=http://<laptop-ip>:8000` on the phone.
- [ ] Load each scenario on the laptop and confirm the phone follows live, including scenario/map dimension changes.
- [ ] Stop the backend and confirm the red disconnected banner appears.
- [ ] Restart the backend and confirm the monitor reconnects automatically.
=======
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
>>>>>>> fe7cedd49db728a25511e5dbefff20046c76ffcb
