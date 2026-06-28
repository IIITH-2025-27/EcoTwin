from celery import Celery
from celery.signals import worker_process_init

from app.core.config import settings

celery_app = Celery(
    "ecotwin",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.workers.tasks.report_tasks",
        "app.ML_pipeline.pipeline",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3_600,  # 1 hour
    task_routes={
        "app.workers.tasks.report_tasks.*": {"queue": "reports"},
        "app.ML_pipeline.pipeline.*":        {"queue": "pipeline"},
    },
)


@worker_process_init.connect
def _init_gee_on_worker_start(**_kwargs) -> None:
    """Pre-initialize GEE in pipeline workers so Phase 1 fails fast with a clear log."""
    import structlog

    log = structlog.get_logger(__name__)
    try:
        from app.ML_pipeline.gee_init import ensure_gee_initialized

        ensure_gee_initialized()
    except Exception as exc:
        # Non-fatal when PRITHVI_USE_STUB=true; Phase 1 will use stub data instead.
        log.warning("GEE init skipped on worker start", error=str(exc))
