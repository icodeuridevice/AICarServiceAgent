from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import garage_agent.routes.jobcards as jobcards_route


def _build_client(db: MagicMock) -> TestClient:
    app = FastAPI()
    app.include_router(jobcards_route.router)
    app.dependency_overrides[jobcards_route.require_staff] = (
        lambda: SimpleNamespace(garage_id=99, role="STAFF")
    )
    app.dependency_overrides[jobcards_route.get_db] = lambda: db
    return TestClient(app)


def test_create_job_card_accepts_json_body(monkeypatch):
    db = MagicMock()
    create_job_card = MagicMock(return_value=SimpleNamespace(id=17, status="IN_PROGRESS"))
    monkeypatch.setattr(jobcards_route, "create_job_card", create_job_card)
    client = _build_client(db)

    response = client.post("/jobcards/", json={"booking_id": 123})

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {"jobcard_id": 17, "status": "IN_PROGRESS"},
        "message": None,
    }
    create_job_card.assert_called_once_with(
        db=db,
        booking_id=123,
        technician_name=None,
        garage_id=99,
    )


def test_create_job_card_rejects_query_param_only(monkeypatch):
    db = MagicMock()
    create_job_card = MagicMock()
    monkeypatch.setattr(jobcards_route, "create_job_card", create_job_card)
    client = _build_client(db)

    response = client.post("/jobcards/?booking_id=123")

    assert response.status_code == 422
    create_job_card.assert_not_called()
