from fastapi.testclient import TestClient

import backend.main as main_module


client = TestClient(main_module.app)


def test_health_endpoint_shape() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200

    payload = response.json()
    assert payload["status"] == "ok"
    assert isinstance(payload.get("rate_limit_rpm"), int)
    assert isinstance(payload.get("cors_origins"), list)
    assert "keys_configured" in payload


def test_research_depth_validation_rejects_invalid_value() -> None:
    response = client.post(
        "/api/research",
        json={"query": "test query", "depth": "invalid-depth"},
    )
    assert response.status_code == 422


def test_markdown_export_success(monkeypatch) -> None:
    sample = {
        "id": "abc123",
        "query": "sample query",
        "timestamp": "2026-03-29T00:00:00",
        "debate": {},
        "timeline": {},
        "mindmap": {},
        "verify": {},
        "search_summary": [],
    }

    monkeypatch.setattr(
        main_module.memory,
        "get_by_id",
        lambda research_id: sample if research_id == "abc123" else None,
    )

    response = client.get("/api/export/markdown/abc123")
    assert response.status_code == 200
    assert "Nexus Research Report" in response.text
    assert "text/markdown" in response.headers.get("content-type", "")


def test_markdown_export_not_found(monkeypatch) -> None:
    monkeypatch.setattr(main_module.memory, "get_by_id", lambda _research_id: None)

    response = client.get("/api/export/markdown/missing")
    assert response.status_code == 404
