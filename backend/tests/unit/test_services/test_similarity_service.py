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
