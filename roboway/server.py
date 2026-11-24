from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from .simulation import Simulation

logger = logging.getLogger(__name__)
SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios"

sim = Simulation()
sim_lock = asyncio.Lock()
broadcast_lock = asyncio.Lock()
clients: set[WebSocket] = set()
event_cursor = 0
event_generation = -1
simulation_generation = 0


class RequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AddJobBody(RequestBody):
    pickup_id: str
    drop_id: str


class EditJobBody(RequestBody):
    pickup_id: str
    drop_id: str


class ValidateJobBody(RequestBody):
    job_id: str
    pickup_id: str
    drop_id: str


class CellBody(RequestBody):
    x: int
    y: int


class SpeedBody(RequestBody):
    speed: float


def _error(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "error": code, "message": message},
    )


def _result_error(result: dict) -> JSONResponse:
    code = result.get("error", "SIMULATION_ERROR")
    status_code = 404 if code in {"JOB_NOT_FOUND", "ROBOT_NOT_FOUND", "SCENARIO_NOT_FOUND"} else 400
    return _error(code, result.get("message", "The simulation command failed"), status_code)


def _scenario_path(scenario_id: str) -> Path | None:
    path = (SCENARIOS_DIR / f"{scenario_id}.json").resolve()
    if path.parent != SCENARIOS_DIR.resolve() or not path.is_file():
        return None
    return path


def _load_scenario_data(scenario_id: str) -> dict | None:
    path = _scenario_path(scenario_id)
    if path is None:
        return None
    import json

    with path.open(encoding="utf-8") as file:
        return json.load(file)


async def _capture_broadcast() -> tuple[dict, list[dict]]:
    global event_cursor, event_generation
    async with sim_lock:
        state = sim.snapshot()
        if event_generation != simulation_generation:
            event_cursor = 0
            event_generation = simulation_generation
        events = sim.events_since(event_cursor)
        if events:
            event_cursor = events[-1]["id"]
    return state, events


async def _send_messages(websocket: WebSocket, state: dict, events: list[dict]) -> None:
    await websocket.send_json({"type": "state", "data": state})
    for event in events:
        await websocket.send_json({"type": "event", "data": event})


async def _broadcast_state() -> dict:
    async with broadcast_lock:
        state, events = await _capture_broadcast()

        async def send_to_client(websocket: WebSocket) -> None:
            try:
                await asyncio.wait_for(_send_messages(websocket, state, events), timeout=1.0)
            except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError, OSError):
                clients.discard(websocket)

        await asyncio.gather(*(send_to_client(client) for client in tuple(clients)))
    return state


async def _broadcast_error(code: str, message: str) -> None:
    async def send_to_client(websocket: WebSocket) -> None:
        try:
            await asyncio.wait_for(
                websocket.send_json({"type": "error", "code": code, "message": message}),
                timeout=1.0,
            )
        except (WebSocketDisconnect, RuntimeError, asyncio.TimeoutError, OSError):
            clients.discard(websocket)

    await asyncio.gather(*(send_to_client(client) for client in tuple(clients)))


async def tick_once() -> dict:
    """Advance exactly one engine tick and broadcast the resulting state."""
    async with sim_lock:
        sim.tick()
    return await _broadcast_state()


async def _simulation_loop() -> None:
    while True:
        try:
            async with sim_lock:
                state = sim.snapshot()
            if state["status"] != "running":
                await asyncio.sleep(0.1)
                continue

            await asyncio.sleep(0.5 / state["speed"])
            async with sim_lock:
                state = sim.snapshot()
                if state["status"] != "running":
                    continue
                sim.tick()
            await _broadcast_state()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Simulation loop iteration failed")
            try:
                await _broadcast_error("SIMULATION_LOOP_ERROR", str(exc))
            except Exception:
                logger.exception("Failed to broadcast simulation loop error")
            await asyncio.sleep(0.1)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global event_cursor, event_generation, simulation_generation
    global sim_lock, broadcast_lock

    sim_lock = asyncio.Lock()
    broadcast_lock = asyncio.Lock()
    async with sim_lock:
        scenario = _load_scenario_data("narrow_passage")
        if scenario is None:
            raise RuntimeError("The default narrow_passage scenario is missing")
        sim.load_scenario(scenario)
        simulation_generation += 1
        event_cursor = 0
        event_generation = -1

    app.state.tick_once = tick_once
    loop_task = asyncio.create_task(_simulation_loop(), name="roboway-simulation-loop")
    try:
        yield
    finally:
        loop_task.cancel()
        with suppress(asyncio.CancelledError):
            await loop_task


app = FastAPI(title="ROBOWAY Simulation API", lifespan=lifespan)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
origins.extend(
    origin.strip()
    for origin in os.environ.get("ROBOWAY_CORS_ORIGINS", "").split(",")
    if origin.strip()
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys(origins)),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def invalid_request_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error("INVALID_REQUEST", "Request body or parameters are invalid")


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/api/state")
async def get_state() -> dict:
    async with sim_lock:
        return sim.snapshot()


@app.get("/api/scenarios")
async def list_scenarios() -> dict:
    import json

    scenarios = []
    for path in sorted(SCENARIOS_DIR.glob("*.json")):
        with path.open(encoding="utf-8") as file:
            scenario = json.load(file)
        scenarios.append({
            "id": scenario["id"],
            "name": scenario["name"],
            "description": scenario["description"],
        })
    return {"scenarios": scenarios}


@app.post("/api/scenarios/{scenario_id}/load")
async def load_scenario(scenario_id: str):
    global simulation_generation
    scenario = _load_scenario_data(scenario_id)
    if scenario is None:
        return _error("SCENARIO_NOT_FOUND", f"Scenario {scenario_id} does not exist", 404)
    async with sim_lock:
        sim.load_scenario(scenario)
        simulation_generation += 1
    await _broadcast_state()
    return {"ok": True}


@app.post("/api/sim/start")
async def start_simulation() -> dict:
    async with sim_lock:
        sim.start()
    await _broadcast_state()
    return {"ok": True, "status": "running"}


@app.post("/api/sim/pause")
async def pause_simulation() -> dict:
    async with sim_lock:
        sim.pause()
    await _broadcast_state()
    return {"ok": True, "status": "paused"}


@app.post("/api/sim/speed")
async def set_speed(body: SpeedBody):
    if body.speed not in {0.5, 1.0, 2.0, 4.0}:
        return _error("INVALID_SPEED", "speed must be one of 0.5, 1, 2, or 4")
    async with sim_lock:
        result = sim.set_speed(body.speed)
        if isinstance(result, dict) and not result.get("ok", True):
            return _result_error(result)
    await _broadcast_state()
    return {"ok": True, "speed": body.speed}


@app.post("/api/jobs")
async def add_job(body: AddJobBody) -> dict:
    async with sim_lock:
        job_id = sim.add_job(body.pickup_id, body.drop_id)
    await _broadcast_state()
    return {"ok": True, "job_id": job_id}


@app.post("/api/jobs/validate")
async def validate_job(body: ValidateJobBody):
    async with sim_lock:
        result = sim.validate_job_edit(body.job_id, body.pickup_id, body.drop_id)
    if not result.get("ok"):
        return _result_error(result)
    return result


@app.patch("/api/jobs/{job_id}")
async def edit_job(job_id: str, body: EditJobBody):
    async with sim_lock:
        result = sim.edit_job(job_id, body.pickup_id, body.drop_id)
    if not result.get("ok"):
        return _result_error(result)
    if result.get("result") == "valid":
        await _broadcast_state()
    return result


@app.post("/api/cells/block")
async def block_cell(body: CellBody):
    async with sim_lock:
        result = sim.block_cell(body.x, body.y)
    if not result.get("ok"):
        return _result_error(result)
    await _broadcast_state()
    return result


@app.post("/api/cells/unblock")
async def unblock_cell(body: CellBody):
    async with sim_lock:
        result = sim.unblock_cell(body.x, body.y)
    if not result.get("ok"):
        return _result_error(result)
    await _broadcast_state()
    return result


@app.post("/api/robots/{robot_id}/fail")
async def fail_robot(robot_id: str):
    async with sim_lock:
        result = sim.fail_robot(robot_id)
    if not result.get("ok"):
        return _result_error(result)
    await _broadcast_state()
    return result


@app.get("/api/events")
async def get_events(since: int = 0) -> dict:
    async with sim_lock:
        return {"events": sim.events_since(since)}


@app.get("/api/metrics")
async def get_metrics() -> dict:
    async with sim_lock:
        return sim.snapshot()["metrics"]


@app.websocket("/ws")
async def websocket_state(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        async with broadcast_lock:
            async with sim_lock:
                state = sim.snapshot()
            await websocket.send_json({"type": "state", "data": state})
            clients.add(websocket)
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        pass
    except (RuntimeError, OSError):
        pass
    finally:
        clients.discard(websocket)
