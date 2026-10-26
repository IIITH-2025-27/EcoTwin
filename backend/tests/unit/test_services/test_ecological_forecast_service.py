from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import ecological_forecast_service as eco
from app.services.ecological_forecast_service import EcologicalForecastService
from app.services.index_calculator import compute_ecological_indices


def _bands(b5: float, b7: float = 300.0) -> dict:
    """Band means as stored in lake_features (reflectance × 10000)."""
    return {
        "b2_mean": 600.0, "b3_mean": 700.0, "b4_mean": 500.0,
        "b5_mean": b5, "b6_mean": 350.0, "b7_mean": b7, "b8_mean": 250.0,
    }


def test_red_edge_slope_uses_true_reflectance_per_100nm():
    indices = compute_ecological_indices(**_bands(b5=500.0, b7=300.0))

    # (0.03 − 0.05) / 78 nm × 100 nm
    assert indices["red_edge_slope"] == pytest.approx(-0.02 / 78 * 100)


def test_ratio_indices_are_unchanged_by_reflectance_scale():
    stored = compute_ecological_indices(**_bands(b5=500.0))
    reflectance = compute_ecological_indices(
        **{k: v / 10000 for k, v in _bands(b5=500.0).items()}
    )

    for key in ("ndci", "ndvi", "ndwi", "turbidity_ratio"):
        assert stored[key] == pytest.approx(reflectance[key])


def test_direction_thresholds_are_half_the_median_change_per_horizon():
    # 40 lakes whose index rises by 0.02 per year → |Δ| = 0.02 × h
    indices_by_lake = {
        lake: {2020 + y: {k: 0.02 * y for k in eco._INDEX_KEYS} for y in range(6)}
        for lake in range(40)
    }

    thresholds = eco._compute_direction_thresholds(indices_by_lake)

    for key in eco._INDEX_KEYS:
        for h in (1, 2, 3):
            assert thresholds[key][h] == pytest.approx(0.5 * 0.02 * h)


def test_direction_thresholds_fall_back_with_too_few_samples():
    indices_by_lake = {1: {2020: {"ndci": 0.1}, 2021: {"ndci": 0.3}}}

    thresholds = eco._compute_direction_thresholds(indices_by_lake)

    assert thresholds["ndci"][1] == eco._FALLBACK_THRESHOLDS["ndci"]
    assert thresholds["red_edge_slope"][3] == eco._FALLBACK_THRESHOLDS["red_edge_slope"]


def test_classify_uses_given_threshold():
    assert eco._classify(0.02, 3, threshold=0.01) == "up"
    assert eco._classify(-0.02, 3, threshold=0.01) == "down"
    assert eco._classify(0.02, 3, threshold=0.05) == "stable"
    assert eco._classify(0.02, 1, threshold=0.01) == "uncertain"


@pytest.mark.asyncio
async def test_forecast_is_anchored_on_query_year(monkeypatch):
    region_id = uuid4()
    region = SimpleNamespace(region_id=region_id, lake_id=1, year=2025)
    region_repo = SimpleNamespace(get_by_id=lambda _id: _async(region))

    anchor_calls = []

    async def fake_anchor(_session, lake_id, max_year=None):
        anchor_calls.append(max_year)
        return {"year": 2022, **_bands(b5=500.0)}

    async def fake_thresholds(_session):
        return {k: {h: 0.001 for h in (1, 2, 3)} for k in eco._INDEX_KEYS}

    async def fake_twin_rows(_session, twins):
        # Both twins' NDCI rises year on year after the matched year 2019
        return {
            twin: [{"year": 2019 + y, **_bands(b5=500.0 + 50 * y)} for y in range(4)]
            for twin in twins
        }

    monkeypatch.setattr(eco, "_fetch_latest_band_row", fake_anchor)
    monkeypatch.setattr(eco, "_load_direction_thresholds", fake_thresholds)
    monkeypatch.setattr(eco, "_fetch_band_rows_for_twins", fake_twin_rows)

    analogs = [
        SimpleNamespace(region_id=uuid4(), lake_id=lake, year=2019, similarity_score=0.9)
        for lake in (2, 3)
    ]
    service = EcologicalForecastService(session=None, region_repo=region_repo, embedding_repo=None)

    result = await service.generate_ecological_forecast(
        region_id=region_id, year=2023, precomputed_analogs=analogs,
    )

    assert anchor_calls == [2023]
    assert result.current_year == 2022  # no band data for 2023 → latest earlier year
    assert result.forecast_years == [2024, 2025, 2026]
    ndci = next(f for f in result.index_forecasts if f.index_name == "ndci")
    assert [d.year for d in ndci.yearly_directions] == [2024, 2025, 2026]
    assert all(d.direction == "up" and d.threshold == 0.001 for d in ndci.yearly_directions)


async def _async(value):
    return value
