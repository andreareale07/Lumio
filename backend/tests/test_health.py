async def test_health_is_always_ok(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_reports_dependency_checks(client):
    response = await client.get("/ready")
    body = response.json()

    assert "database" in body["checks"]
    assert "redis" in body["checks"]
    if body["status"] == "ok":
        assert response.status_code == 200
        assert body["checks"] == {"database": "ok", "redis": "ok"}
    else:
        assert response.status_code == 503
