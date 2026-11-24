import pytest
from fastapi.testclient import TestClient

from roboway.server import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _tick(client: TestClient, count: int = 1) -> None:
    for _ in range(count):
        client.portal.call(client.app.state.tick_once)


def test_state_matches_contract_and_startup_is_paused(client):
    response = client.get("/api/state")
    assert response.status_code == 200
    state = response.json()
    assert set(state) == {
        "tick", "status", "speed", "scenario_id", "grid", "robots", "jobs",
        "reservations_count", "deadlock", "metrics", "events_tail",
    }
    assert state["scenario_id"] == "narrow_passage"
    assert state["status"] == "paused"


def test_rest_load_and_tick_helper_complete_all_scenarios(client):
    for scenario_id in ("narrow_passage", "failed_robot", "blocked_aisle"):
        assert client.post(f"/api/scenarios/{scenario_id}/load").json() == {"ok": True}
        assert client.post("/api/sim/start").json()["status"] == "running"
        _tick(client, 80)
        state = client.get("/api/state").json()
        assert all(job["state"] == "Delivered" for job in state["jobs"])
        assert state["metrics"]["invariant_violations"] == 0


def test_add_job_while_running_is_visible_in_snapshot(client):
    client.post("/api/sim/start")
    response = client.post("/api/jobs", json={"pickup_id": "P1", "drop_id": "D1"})
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    state = client.get("/api/state").json()
    assert any(job["id"] == job_id for job in state["jobs"])


def test_occupied_cell_error_and_fail_robot_response(client):
    state = client.get("/api/state").json()
    x, y = state["robots"][0]["pos"]
    blocked = client.post("/api/cells/block", json={"x": x, "y": y})
    assert blocked.status_code == 400
    assert blocked.json()["error"] == "CELL_OCCUPIED"

    client.post("/api/sim/start")
    _tick(client)
    failed = client.post("/api/robots/R1/fail")
    assert failed.status_code == 200
    assert failed.json() == {"ok": True, "carrying_job": "J1"}


def test_job_edit_lock_and_validation_are_non_mutating(client):
    initial = client.get("/api/state").json()
    waiting_job = initial["jobs"][0]
    before_validation = client.get("/api/state").json()
    validated = client.post(
        "/api/jobs/validate",
        json={
            "job_id": waiting_job["id"],
            "pickup_id": waiting_job["pickup_id"],
            "drop_id": waiting_job["drop_id"],
        },
    )
    after_validation = client.get("/api/state").json()
    assert validated.status_code == 200
    assert validated.json()["ok"] is True
    assert before_validation == after_validation

    client.post("/api/sim/start")
    _tick(client)
    client.post("/api/sim/pause")
    before = client.get("/api/state").json()
    picked_job = next(job for job in before["jobs"] if job["state"] == "PickedUp")

    locked = client.patch(
        f"/api/jobs/{picked_job['id']}",
        json={"pickup_id": picked_job["pickup_id"], "drop_id": picked_job["drop_id"]},
    )
    assert locked.status_code == 400
    assert locked.json()["error"] == "JOB_LOCKED"


def test_malformed_body_uses_invalid_request_shape(client):
    response = client.post("/api/jobs", json={"pickup_id": "P1"})
    assert response.status_code == 400
    assert response.json() == {
        "ok": False,
        "error": "INVALID_REQUEST",
        "message": "Request body or parameters are invalid",
    }


def test_websocket_receives_state_on_connect_and_after_commands(client):
    with client.websocket_connect("/ws") as websocket:
        first = websocket.receive_json()
        assert first["type"] == "state"
        response = client.post("/api/jobs", json={"pickup_id": "P1", "drop_id": "D1"})
        assert response.status_code == 200
        after_command = websocket.receive_json()
        assert after_command["type"] == "state"
        assert any(job["id"] == response.json()["job_id"] for job in after_command["data"]["jobs"])


def test_speed_must_be_one_of_allowed_values(client):
    response = client.post("/api/sim/speed", json={"speed": 3})
    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_SPEED"


def test_scenario_list_and_health_endpoints(client):
    assert client.get("/health").json() == {"ok": True}
    scenarios = client.get("/api/scenarios").json()["scenarios"]
    assert {scenario["id"] for scenario in scenarios} == {"narrow_passage", "failed_robot", "blocked_aisle"}
