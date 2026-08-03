from types import SimpleNamespace

import pytest

from app.schemas.similarity import SimilarityMethod
from app.services.similarity_service import SimilarityService


def test_select_query_trajectory_uses_last_five_years():
    service = SimilarityService.__new__(SimilarityService)
    records = [
        (2020, [0.0]),
        (2021, [0.0]),
        (2022, [0.0]),
        (2023, [0.0]),
        (2024, [0.0]),
        (2025, [0.0]),
    ]

    trajectory = service._select_query_trajectory(records, anchor_year=2025, window_size=5)

    assert [year for year, _ in trajectory] == [2021, 2022, 2023, 2024, 2025]


def test_build_candidate_windows_returns_all_sliding_windows():
    service = SimilarityService.__new__(SimilarityService)
    records = [
        (2020, [0.0]),
        (2021, [0.0]),
        (2022, [0.0]),
        (2023, [0.0]),
        (2024, [0.0]),
        (2025, [0.0]),
    ]

    windows = service._build_candidate_windows(records, window_size=5)

    assert len(windows) == 2
    assert [year for year, _ in windows[0]] == [2020, 2021, 2022, 2023, 2024]
    assert [year for year, _ in windows[1]] == [2021, 2022, 2023, 2024, 2025]


def test_compute_window_similarity_uses_mean_of_pairwise_scores():
    service = SimilarityService.__new__(SimilarityService)
    query_window = [(2021, [1.0, 0.0]), (2022, [0.0, 1.0])]
    candidate_window = [(2021, [1.0, 0.0]), (2022, [0.0, 1.0])]

    score = service._compute_window_similarity(
        query_window,
        candidate_window,
        method=SimilarityMethod.COSINE,
    )

    assert score == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_search_analogs_returns_matched_year_window():
    class FakeRegionRepo:
        async def get_by_id(self, region_id):
            return SimpleNamespace(region_id=region_id, lake_id=1)

    class FakeEmbeddingRepo:
        async def get_historical_embeddings_for_region(self, region_id):
            return [
                SimpleNamespace(year=2020, embedding=[0.0]),
                SimpleNamespace(year=2021, embedding=[1.0]),
                SimpleNamespace(year=2022, embedding=[1.0]),
                SimpleNamespace(year=2023, embedding=[1.0]),
                SimpleNamespace(year=2024, embedding=[1.0]),
                SimpleNamespace(year=2025, embedding=[1.0]),
            ]

        async def get_all_historical_embeddings(self):
            return [
                {
                    "region_id": "22222222-2222-2222-2222-222222222222",
                    "lake_id": 2,
                    "center_lat": 12.34,
                    "center_lon": 56.78,
                    "area_sqkm": 42.0,
                    "dominant_ecosystem": "Wetland",
                    "records": [
                        SimpleNamespace(year=2020, embedding=[0.0]),
                        SimpleNamespace(year=2021, embedding=[1.0]),
                        SimpleNamespace(year=2022, embedding=[1.0]),
                        SimpleNamespace(year=2023, embedding=[1.0]),
                        SimpleNamespace(year=2024, embedding=[1.0]),
                        SimpleNamespace(year=2025, embedding=[1.0]),
                    ],
                }
            ]

    service = SimilarityService(FakeEmbeddingRepo(), FakeRegionRepo())
    response = await service.search_analogs(
        region_id="11111111-1111-1111-1111-111111111111",
        top_k=1,
        method=SimilarityMethod.COSINE,
    )

    assert response.analogs[0].start_year == 2021
    assert response.analogs[0].end_year == 2025
    assert response.analogs[0].year == 2025
