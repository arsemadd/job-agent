"""CareerOS Background Autonomous Scheduler.

Runs periodic sourcing runs (collect -> filter -> score -> notify) in a background thread
when deployed to an always-on cloud host (Render, Railway, Fly.io, or VPS).
"""
import logging
import os
import threading
import time

logger = logging.getLogger("careeros.scheduler")

_scheduler_thread = None
_stop_event = threading.Event()


def start_scheduler(interval_hours: float = 1.0):
    """Starts the background periodic sourcing loop."""
    global _scheduler_thread, _stop_event

    # Allow disabling via env var (e.g. when using GitHub Actions cron instead)
    if os.environ.get("ENABLE_BACKGROUND_SCHEDULER", "0").lower() not in {"1", "true", "yes"}:
        logger.info("Background scheduler disabled (using external cron or GitHub Actions).")
        return

    if _scheduler_thread and _scheduler_thread.is_alive():
        logger.info("Background scheduler already running.")
        return

    _stop_event.clear()

    def _loop():
        logger.info(f"CareerOS background scheduler active (interval: {interval_hours}h).")
        # Initial sleep on startup to let server settle
        time.sleep(30)
        while not _stop_event.is_set():
            try:
                from backend.pipeline import run as run_pipeline
                logger.info("Executing scheduled sourcing run...")
                run_pipeline(dry_run=False, skip_notify=False)
                logger.info("Scheduled sourcing run completed successfully.")
            except Exception as e:
                logger.error(f"Error during scheduled sourcing run: {e}")

            # Sleep in 10-second increments so stop event responds promptly
            sleep_seconds = int(interval_hours * 3600)
            for _ in range(sleep_seconds // 10):
                if _stop_event.is_set():
                    break
                time.sleep(10)

    _scheduler_thread = threading.Thread(target=_loop, daemon=True, name="CareerOSSourcingScheduler")
    _scheduler_thread.start()


def stop_scheduler():
    global _stop_event
    _stop_event.set()
