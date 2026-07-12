"""Lake search and geometry endpoints for the interactive map."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from geoalchemy2.shape import to_shape
from sqlalchemy import distinct, func, select

from app.core.dependencies import DatabaseDep
from app.models.lake import Lake
from app.schemas.lake import LakeCountResponse, LakeGeometryResponse, LakeMarkerResponse, LakeSearchResponse

router = APIRouter(tags=["Lakes"])


@router.get("/count", response_model=LakeCountResponse)
async def get_lake_count(
    db: DatabaseDep,
    country: str = Query("India", min_length=1, max_length=100),
) -> LakeCountResponse:
    """Return the number of active lakes available for a country."""
    normalized_country = country.strip()
    total_lakes = await db.scalar(
        select(func.count()).select_from(Lake).where(
            Lake.country.ilike(normalized_country),
            Lake.is_active.is_(True),
        ),
    )
    return LakeCountResponse(country=normalized_country, total_lakes=total_lakes or 0)


@router.get("/markers", response_model=list[LakeMarkerResponse])
async def get_lake_markers(
    db: DatabaseDep,
    country: str = Query("India", min_length=1, max_length=100),
) -> list[LakeMarkerResponse]:
    """
    Return centroid coordinates for all active lakes so the map can render
    a lightweight pin/marker layer without fetching full geometries.

    Uses the ``centroid`` column; falls back to ``pour_lat`` / ``pour_long``
    for lakes that have a pour point but no computed centroid.
    """
    normalized_country = country.strip()
    statement = select(Lake).where(
        Lake.country.ilike(normalized_country),
        Lake.is_active.is_(True),
        # Require at least one coordinate source
        (Lake.centroid.isnot(None)) | (Lake.pour_lat.isnot(None)),
    )
    rows = (await db.execute(statement)).scalars().all()

    markers: list[LakeMarkerResponse] = []
    for lake in rows:
        if lake.centroid is not None:
            point = to_shape(lake.centroid)
            lat, lon = point.y, point.x
        elif lake.pour_lat is not None and lake.pour_long is not None:
            lat, lon = lake.pour_lat, lake.pour_long
        else:
            continue   # skip if no coordinate at all
        markers.append(
            LakeMarkerResponse(
                lake_id=lake.lake_id,
                display_name=lake.display_name,
                state=lake.state,
                area_sqkm=lake.area_sqkm,
                center_lat=lat,
                center_lon=lon,
            )
        )
    return markers


@router.get("/search", response_model=list[LakeSearchResponse])
async def search_lakes(
    db: DatabaseDep,
    query: str = Query(..., min_length=3, max_length=100),
    limit: int = Query(10, ge=1, le=20),
) -> list[LakeSearchResponse]:
    """Return display-name suggestions after at least three characters."""
    term = query.strip()
    if len(term) < 3:
        return []

    # Escape SQL LIKE wildcards so user input is always treated as text.
    escaped_term = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    statement = (
        select(Lake.lake_id, Lake.display_name, Lake.state, Lake.area_sqkm)
        .where(
            Lake.country.ilike("India"),
            Lake.is_active.is_(True),
            Lake.display_name.ilike(f"%{escaped_term}%", escape="\\"),
        )
        .order_by(Lake.display_name.asc())
        .limit(limit)
    )
    rows = (await db.execute(statement)).all()
    return [
        LakeSearchResponse(
            lake_id=row.lake_id,
            display_name=row.display_name,
            state=row.state,
            area_sqkm=row.area_sqkm,
        )
        for row in rows
    ]


@router.get("/states", response_model=list[str])
async def get_lake_states(
    db: DatabaseDep,
    country: str = Query("India", min_length=1, max_length=100),
) -> list[str]:
    """Return sorted distinct state names for active lakes in the given country."""
    normalized_country = country.strip()
    rows = (
        await db.execute(
            select(distinct(Lake.state))
            .where(
                Lake.country.ilike(normalized_country),
                Lake.is_active.is_(True),
                Lake.state.isnot(None),
            )
            .order_by(Lake.state.asc())
        )
    ).scalars().all()
    return [r for r in rows if r]  # filter out empty strings


@router.get("/{lake_id}", response_model=LakeGeometryResponse)
async def get_lake_geometry(lake_id: int, db: DatabaseDep) -> LakeGeometryResponse:
    """Return the stored lake polygon for map highlighting."""
    lake = await db.scalar(
        select(Lake).where(Lake.lake_id == lake_id, Lake.is_active.is_(True)),
    )
    if lake is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lake {lake_id} was not found.",
        )

    geometry = to_shape(lake.geom).__geo_interface__ if lake.geom is not None else None
    centroid = to_shape(lake.centroid) if lake.centroid is not None else None
    return LakeGeometryResponse(
        lake_id=lake.lake_id,
        display_name=lake.display_name,
        state=lake.state,
        area_sqkm=lake.area_sqkm,
        country=lake.country,
        center_lat=centroid.y if centroid is not None else lake.pour_lat,
        center_lon=centroid.x if centroid is not None else lake.pour_long,
        geometry=geometry,
    )
