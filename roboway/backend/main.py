from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from simulation import simulation


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)
        await websocket.send_json(simulation.snapshot())

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, data: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for connection in tuple(self.connections):
            try:
                await connection.send_json(data)
            except (RuntimeError, WebSocketDisconnect):
                stale.append(connection)
        for connection in stale:
            self.disconnect(connection)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(simulation_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="RoboWay Simulation API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def simulation_loop() -> None:
    while True:
        await asyncio.sleep(0.65)
        if simulation.snapshot()["running"]:
            await manager.broadcast(simulation.step())


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "roboway-simulation"}


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return simulation.snapshot()


@app.post("/api/simulation/{action}")
async def control_simulation(action: str) -> dict[str, Any]:
    actions = {"start": simulation.start, "pause": simulation.pause, "reset": simulation.reset, "step": simulation.step}
    handler = actions.get(action)
    if handler is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=f"Unknown simulation action: {action}")
    state = handler()
    await manager.broadcast(state)
    return state


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
