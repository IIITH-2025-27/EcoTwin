from pathlib import Path

from app.models.region import Region

BACKEND_ROOT = Path(__file__).resolve().parents[3]
EXPECTED_UPSERT_FRAGMENTS = (
    "region_id, lake_id, year, center_lat, center_lon",
    "gen_random_uuid(), lake.lake_id, :year",
    "COALESCE(ST_Y(lake.centroid), ST_Y(ST_Centroid(lake.geom)), lake.pour_lat, 0)",
    "COALESCE(ST_X(lake.centroid), ST_X(ST_Centroid(lake.geom)), lake.pour_long, 0)",
    "ON CONFLICT ON CONSTRAINT uq_regions_lake_year DO UPDATE SET",
)


def test_region_has_uuid_primary_key_and_lake_year_unique_constraint():
    columns = Region.__table__.c

    assert list(Region.__table__.primary_key.columns.keys()) == ["region_id"]
    assert {"region_id", "lake_id", "year", "center_lat", "center_lon", "embedding", "status"} <= set(
        columns.keys()
    )
    assert "uq_regions_lake_year" in {
        constraint.name for constraint in Region.__table__.constraints
    }


def test_lake_embedding_upsert_sql_maps_region_columns():
    for relative_path in (
        "app/embedding_pipeline/storage.py",
        "app/embedding_pipeline/lake_aggregator.py",
    ):
        source = (BACKEND_ROOT / relative_path).read_text()
        for fragment in EXPECTED_UPSERT_FRAGMENTS:
            assert fragment in source, f"Missing `{fragment}` in {relative_path}"
