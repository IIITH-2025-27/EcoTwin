import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_get_nonexistent_region_returns_404(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/v1/regions/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_find_region_missing_body_returns_422(client: AsyncClient) -> None:
    response = await client.post("/api/v1/regions/query", json={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_find_region_invalid_lat_returns_422(client: AsyncClient) -> None:
    response = await client.post("/api/v1/regions/query", json={"lat": 999, "lon": 0})
    assert response.status_code == 422
