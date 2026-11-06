import time

from fastapi.testclient import TestClient

from data_agent.api import create_app
from data_agent.evaluation.cases import CASES
from data_agent.store import RunStore


def wait(client, run_id):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        run = client.get(f"/v1/analyses/{run_id}").json()
        if run["status"] not in {"queued", "running"}:
            return run
        time.sleep(0.05)
    raise AssertionError("API task timeout")


def test_api_clarification_resume_artifacts_and_missing_key(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json()["live_model_configured"] is False
        assert client.get("/v1/datasets").json()[0]["dataset_id"] == "synthetic"
        assert (
            client.post(
                "/v1/analyses", json={"question": CASES[0]["question"]}
            ).status_code
            == 409
        )
        response = client.post(
            "/v1/analyses", json={"question": CASES[12]["question"], "mode": "demo"}
        )
        assert response.status_code == 202
        run_id = response.json()["run_id"]
        assert wait(client, run_id)["status"] == "needs_clarification"
        assert (
            client.post(
                f"/v1/analyses/{run_id}/clarifications",
                json={"metric": "gift_coverage"},
            ).status_code
            == 202
        )
        run = wait(client, run_id)
        assert run["status"] == "completed", run.get("error")
        assert run["previous_attempts"]
        assert (
            client.get(f"/v1/analyses/{run_id}/artifacts/report.html").status_code
            == 200
        )
        assert client.get(f"/v1/analyses/{run_id}/artifacts/.env").status_code == 404
        assert (
            client.post(
                f"/v1/analyses/{run_id}/clarifications", json={"metric": "gift_value"}
            ).status_code
            == 409
        )
        assert client.get("/v1/analyses/nonexistent").status_code == 404
        assert (
            client.post(
                "/v1/analyses", json={"question": "hi", "dataset_id": "../../secret"}
            ).status_code
            == 422
        )
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/v1/analyses/{run_id}").json()["status"] == "completed"


def test_restart_marks_interrupted(settings):
    store = RunStore(settings)
    store.put(
        {
            "run_id": "interrupted-test",
            "status": "running",
            "request": {},
            "artifacts": [],
        }
    )
    store.interrupted()
    assert store.get("interrupted-test")["status"] == "failed"
