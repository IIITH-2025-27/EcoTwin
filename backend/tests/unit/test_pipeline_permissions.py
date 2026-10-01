"""Tests for pipeline permission enforcement.

Covers:
  CASE 1 — Master OFF  → all pipeline endpoints return 403
  CASE 2 — Master ON + individual ON  → pipeline endpoint succeeds (non-403)
  CASE 3 — Master ON + individual OFF → pipeline endpoint returns 403
  CASE 4 — Master ON, mixed individual → only enabled ones succeed
  CASE 5 — Master OFF + individual ON → still 403
  CASE 6 — Non-pipeline endpoints unaffected
  CONFIG — GET /api/v1/config returns correct shape
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.pipeline_permission import PipelinePermission


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _set_permission(db_session, key: str, enabled: bool) -> None:
    """Insert or update a single permission row."""
    from sqlalchemy import select, update

    row = (
        await db_session.execute(
            select(PipelinePermission).where(PipelinePermission.permission_key == key)
        )
    ).scalar_one_or_none()

    if row is None:
        db_session.add(
            PipelinePermission(
                permission_key=key,
                display_name=key.replace("_", " ").title(),
                is_enabled=enabled,
            )
        )
    else:
        await db_session.execute(
            update(PipelinePermission)
            .where(PipelinePermission.permission_key == key)
            .values(is_enabled=enabled)
        )
    await db_session.commit()


async def _seed_all_disabled(db_session) -> None:
    """Ensure all 8 default permission rows exist and are disabled."""
    keys = [
        "allow_data_pipeline_run",
        "sync_lakes",
        "fetch_images",
        "merge_image_tiles",
        "generate_embeddings",
        "merge_embeddings",
        "generate_features",
        "fetch_b8",
    ]
    for key in keys:
        await _set_permission(db_session, key, False)


# ── Pipeline endpoints to test (POST method, path, permission_key) ──────────

PIPELINE_ENDPOINTS = [
    ("/api/v1/sync/lakes/import", "sync_lakes"),
    ("/api/v1/imagery/fetch", "fetch_images"),
    ("/api/v1/imagery/merge", "merge_image_tiles"),
    ("/api/v1/embeddings/generate", "generate_embeddings"),
    ("/api/v1/embeddings/merge", "merge_embeddings"),
    ("/api/v1/lake-features/generate", "generate_features"),
    ("/api/v1/lake-features/generate-b8", "fetch_b8"),
]


# ── CASE 1: All disabled (default) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_disabled_returns_403(client: AsyncClient, db_session):
    """When all permissions are FALSE, every pipeline POST must return 403."""
    await _seed_all_disabled(db_session)

    for path, _key in PIPELINE_ENDPOINTS:
        resp = await client.post(path, json={})
        assert resp.status_code == 403, f"{path} expected 403 but got {resp.status_code}"
        assert resp.json()["detail"] == "Data Pipeline run Access denied"


# ── CASE 2: Master ON + individual ON → non-403 ─────────────────────────────

@pytest.mark.asyncio
async def test_master_on_individual_on_allows(client: AsyncClient, db_session):
    """When master + individual are both ON, the endpoint should NOT return 403.

    Note: the endpoint may return 4xx/5xx for other reasons (missing body,
    no data, etc.) — we only verify it's NOT a 403 permission denial.
    """
    await _seed_all_disabled(db_session)
    await _set_permission(db_session, "allow_data_pipeline_run", True)
    await _set_permission(db_session, "sync_lakes", True)

    resp = await client.post("/api/v1/sync/lakes/import", json={})
    assert resp.status_code != 403, (
        f"Expected non-403 but got {resp.status_code}: {resp.text}"
    )


# ── CASE 3: Master ON + individual OFF → 403 ────────────────────────────────

@pytest.mark.asyncio
async def test_master_on_individual_off_returns_403(client: AsyncClient, db_session):
    """Master ON but individual OFF must still return 403."""
    await _seed_all_disabled(db_session)
    await _set_permission(db_session, "allow_data_pipeline_run", True)
    # sync_lakes stays FALSE

    resp = await client.post("/api/v1/sync/lakes/import", json={})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Data Pipeline run Access denied"


# ── CASE 5: Master OFF + individual ON → 403 ────────────────────────────────

@pytest.mark.asyncio
async def test_master_off_individual_on_returns_403(client: AsyncClient, db_session):
    """Master OFF but individual ON must still return 403."""
    await _seed_all_disabled(db_session)
    # master stays FALSE
    await _set_permission(db_session, "sync_lakes", True)

    resp = await client.post("/api/v1/sync/lakes/import", json={})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Data Pipeline run Access denied"


# ── CASE 4: Master ON, mixed individual ──────────────────────────────────────

@pytest.mark.asyncio
async def test_mixed_permissions(client: AsyncClient, db_session):
    """Master ON, sync_lakes ON, fetch_images OFF.

    sync endpoint → non-403
    imagery endpoint → 403
    """
    await _seed_all_disabled(db_session)
    await _set_permission(db_session, "allow_data_pipeline_run", True)
    await _set_permission(db_session, "sync_lakes", True)
    # fetch_images stays FALSE

    resp_sync = await client.post("/api/v1/sync/lakes/import", json={})
    assert resp_sync.status_code != 403

    resp_fetch = await client.post("/api/v1/imagery/fetch", json={})
    assert resp_fetch.status_code == 403


# ── CONFIG endpoint ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_config_endpoint_returns_permissions(client: AsyncClient, db_session):
    """GET /api/v1/config must return the expected permission shape."""
    await _seed_all_disabled(db_session)

    resp = await client.get("/api/v1/config")
    assert resp.status_code == 200

    data = resp.json()
    assert "allow_data_pipeline_run" in data
    assert "pipeline_permissions" in data
    assert isinstance(data["pipeline_permissions"], dict)

    expected_keys = {
        "sync_lakes",
        "fetch_images",
        "merge_image_tiles",
        "generate_embeddings",
        "merge_embeddings",
        "generate_features",
        "fetch_b8",
    }
    assert set(data["pipeline_permissions"].keys()) == expected_keys
    assert data["allow_data_pipeline_run"] is False
    assert all(v is False for v in data["pipeline_permissions"].values())


# ── CASE 6: Non-pipeline endpoints unaffected ───────────────────────────────

@pytest.mark.asyncio
async def test_non_pipeline_endpoints_unaffected(client: AsyncClient, db_session):
    """Read-only / non-pipeline endpoints must still work regardless of permissions."""
    await _seed_all_disabled(db_session)

    # Health check
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200

    # Sync country (read-only, not gated)
    resp = await client.get("/api/v1/sync/country")
    assert resp.status_code == 200

    # Sync status (read-only, not gated)
    resp = await client.get("/api/v1/sync/status")
    assert resp.status_code == 200
