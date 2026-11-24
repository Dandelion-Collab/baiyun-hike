"""只验健康检查与接口占位，不验业务逻辑。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_check_returns_issues() -> None:
    response = client.post("/check", json={"text": "第一天 上午 广东省博物馆"})
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert any(item["rule"] == "closed_day" for item in response.json())


def test_route_returns_result() -> None:
    response = client.post(
        "/route",
        json={"from_node": "N01", "to_node": "N10", "depart_at": "19:00"},
    )
    assert response.status_code == 200
    assert response.json()["reachable"] is True


def test_openapi_documents_both_capabilities() -> None:
    schema = client.get("/openapi.json").json()
    assert "/healthz" in schema["paths"]
    assert "/check" in schema["paths"]
    assert "/route" in schema["paths"]