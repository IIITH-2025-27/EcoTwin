import time
from typing import List, Optional, Sequence, Tuple
from uuid import UUID

import structlog

from app.core.config import settings
from app.core.exceptions import EmbeddingNotFoundException, RegionNotFoundException
from app.repositories.embedding_repository import EmbeddingRepository
from app.repositories.region_repository import RegionRepository
from app.schemas.similarity import AnalogResult, SimilarityMethod, SimilaritySearchResponse

logger = structlog.get_logger(__name__)


class SimilarityService:
    def __init__(
        self,
        embedding_repo: EmbeddingRepository,
        region_repo: RegionRepository,
    ) -> None:
        self._embedding_repo = embedding_repo
        self._region_repo = region_repo

    @staticmethod
    def _select_query_trajectory(
        records: Sequence[Tuple[int, List[float]]],
        anchor_year: Optional[int] = None,
        window_size: int = 5,
    ) -> List[Tuple[int, List[float]]]:
        if not records:
            return []

        ordered = sorted(records, key=lambda item: item[0])
        if anchor_year is None:
            anchor_year = ordered[-1][0]

        anchor_index = next(
            (index for index, (year, _) in enumerate(ordered) if year == anchor_year),
            None,
        )
        if anchor_index is None:
            return []

        start = max(0, anchor_index - window_size + 1)
        end = anchor_index + 1
        return list(ordered[start:end])

    @staticmethod
    def _build_candidate_windows(
        records: Sequence[Tuple[int, List[float]]],
        window_size: int = 5,
    ) -> List[List[Tuple[int, List[float]]]]:
        if len(records) < window_size:
            return []

        ordered = sorted(records, key=lambda item: item[0])
        return [
            list(ordered[index:index + window_size])
            for index in range(len(ordered) - window_size + 1)
        ]

    @staticmethod
    def _compute_window_similarity(
        query_window: Sequence[Tuple[int, List[float]]],
        candidate_window: Sequence[Tuple[int, List[float]]],
        method: SimilarityMethod = SimilarityMethod.COSINE,
    ) -> float:
        if not query_window or not candidate_window:
            return 0.0

        if len(query_window) != len(candidate_window):
            return 0.0

        pair_scores: List[float] = []
        for (_, query_embedding), (_, candidate_embedding) in zip(query_window, candidate_window):
            pair_scores.append(
                SimilarityService._compute_pair_similarity(query_embedding, candidate_embedding, method)
            )

        return sum(pair_scores) / len(pair_scores) if pair_scores else 0.0

    @staticmethod
    def _compute_pair_similarity(
        query_embedding: Sequence[float],
        candidate_embedding: Sequence[float],
        method: SimilarityMethod = SimilarityMethod.COSINE,
    ) -> float:
        if method == SimilarityMethod.EUCLIDEAN:
            distance = sum((a - b) ** 2 for a, b in zip(query_embedding, candidate_embedding)) ** 0.5
            return 1.0 / (1.0 + distance)

        if method == SimilarityMethod.KNN:
            inner_product = sum(a * b for a, b in zip(query_embedding, candidate_embedding))
            return (inner_product + 1.0) / 2.0

        cosine_distance = 0.0
        if sum(a * a for a in query_embedding) > 0 and sum(b * b for b in candidate_embedding) > 0:
            dot = sum(a * b for a, b in zip(query_embedding, candidate_embedding))
            norms = (sum(a * a for a in query_embedding) ** 0.5) * (
                sum(b * b for b in candidate_embedding) ** 0.5
            )
            cosine_distance = 1.0 - (dot / norms) if norms else 0.0
        return 1.0 - cosine_distance

    # Floor below which a cosine/KNN score is treated as zero similarity.
    # All Prithvi embeddings are L2-normalised, so raw cosine scores
    # cluster tightly near 1.0.  Rescaling [_COSINE_FLOOR, 1.0] → [0.0, 1.0]
    # spreads the values so the displayed percentage is meaningful.
    _COSINE_FLOOR: float = 0.5
    @staticmethod
    def _rescale_score(score: float, method: SimilarityMethod) -> float:
        """
        Map a raw similarity score to a human-meaningful [0, 1] range.
        - COSINE / KNN: raw scores cluster near 1.0 for all unit-norm
          embeddings from the same model.  Linearly rescale
          [_COSINE_FLOOR, 1.0] → [0.0, 1.0] so rankings are visible.
        - EUCLIDEAN: 1 / (1 + distance) is already naturally spread;
          no rescaling needed.
        """
        if method in (SimilarityMethod.COSINE, SimilarityMethod.KNN):
            floor = SimilarityService._COSINE_FLOOR
            span = 1.0 - floor
            return max(0.0, min(1.0, (score - floor) / span))
        return max(0.0, min(1.0, score))

    async def search_analogs(
        self,
        region_id: UUID,
        year: Optional[int] = None,
        top_k: int = 10,
        exclude_same_region: bool = True,
        method: SimilarityMethod = SimilarityMethod.COSINE,
    ) -> SimilaritySearchResponse:
        region = await self._region_repo.get_by_id(region_id)
        if not region:
            raise RegionNotFoundException(str(region_id))

        query_lake_id = region.lake_id
        query_records = await self._embedding_repo.get_historical_embeddings_for_region(region_id)
        if not query_records:
            raise EmbeddingNotFoundException(str(region_id))

        # Filter out any records whose embedding is None (defensive guard)
        valid_query_records = [
            r for r in query_records if r.embedding is not None
        ]
        if not valid_query_records:
            raise EmbeddingNotFoundException(str(region_id))

        query_trajectory = self._select_query_trajectory(
            [(record.year, record.embedding) for record in valid_query_records],
            anchor_year=year,
            window_size=5,
        )
        if not query_trajectory:
            raise EmbeddingNotFoundException(str(region_id))

        query_year = query_trajectory[-1][0]

        logger.info(
            "Query trajectory built",
            region_id=str(region_id),
            query_lake_id=query_lake_id,
            trajectory_years=[y for y, _ in query_trajectory],
            embedding_dim=len(query_trajectory[0][1]) if query_trajectory else 0,
        )

        start_time = time.perf_counter()
        candidate_records = await self._embedding_repo.get_all_historical_embeddings()
        logger.info(
            "Candidate lakes fetched",
            candidate_count=len(candidate_records),
        )
        best_matches: List[dict] = []
        for candidate in candidate_records:
            candidate_lake_id = candidate["lake_id"]
            if exclude_same_region and candidate_lake_id == query_lake_id:
                continue

            records = [
                (embedding.year, embedding.embedding)
                for embedding in candidate["records"]
                if embedding.embedding is not None
            ]
            windows = self._build_candidate_windows(records, window_size=5)
            if not windows:
                continue

            best_window_score = -1.0
            best_window = None
            for window in windows:
                window_score = self._compute_window_similarity(query_trajectory, window, method=method)
                if window_score > best_window_score:
                    best_window_score = window_score
                    best_window = window

            if best_window is not None:
                start_year = best_window[0][0]
                end_year = best_window[-1][0]
                best_matches.append(
                    {
                        "region_id": candidate["region_id"],
                        "start_year": start_year,
                        "end_year": end_year,
                        "similarity_score": self._rescale_score(best_window_score, method),
                        "year": end_year,
                        "center_lat": candidate["center_lat"],
                        "center_lon": candidate["center_lon"],
                        "area_sqkm": candidate.get("area_sqkm"),
                        "dominant_ecosystem": candidate["dominant_ecosystem"],
                    }
                )

        best_matches.sort(key=lambda item: item["similarity_score"], reverse=True)
        raw_results = best_matches[: min(top_k, settings.MAX_TOP_K)]
        latency_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            "Similarity search completed",
            region_id=str(region_id),
            year=query_year,
            method=method.value,
            results=len(raw_results),
            latency_ms=round(latency_ms, 1),
        )

        analogs = [
            AnalogResult(
                region_id=row["region_id"],
                center_lat=row["center_lat"],
                center_lon=row["center_lon"],
                area_sqkm=row.get("area_sqkm"),
                similarity_score=self._rescale_score(float(row["similarity_score"]), method),
                year=row["year"],
                start_year=row["start_year"],
                end_year=row["end_year"],
                dominant_ecosystem=row.get("dominant_ecosystem"),
            )
            for row in raw_results
        ]

        return SimilaritySearchResponse(
            query_region_id=region_id,
            query_year=query_year,
            analogs=analogs,
            search_latency_ms=round(latency_ms, 2),
            method=method,
        )
