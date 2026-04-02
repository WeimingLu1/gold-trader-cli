"""APScheduler-based scheduler for the main pipeline."""
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger

_pipeline_run_fn = None


def set_pipeline_fn(fn) -> None:
    """Register the main pipeline function to be called by the scheduler."""
    global _pipeline_run_fn
    _pipeline_run_fn = fn


def build_scheduler(interval_hours: int = 4) -> BlockingScheduler:
    """
    Build and return a BlockingScheduler that runs the pipeline every `interval_hours`.

    Usage:
        scheduler = build_scheduler(interval_hours=4)
        scheduler.start()
    """
    scheduler = BlockingScheduler()

    def _run():
        if _pipeline_run_fn is None:
            logger.error("Pipeline function not registered. Call set_pipeline_fn first.")
            return
        try:
            _pipeline_run_fn()
            logger.info("Scheduled pipeline run completed.")
        except Exception as e:
            logger.exception(f"Scheduled pipeline run failed: {e}")

    scheduler.add_job(
        _run,
        trigger=IntervalTrigger(hours=interval_hours),
        id="gold_trader_pipeline",
        name="Gold Trader Main Pipeline",
        replace_existing=True,
        max_instances=1,
    )

    logger.info(f"Scheduler configured: pipeline runs every {interval_hours}h")
    return scheduler
