# app/scheduler.py
import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

from app.services.scraper_manager import (
    scrape_jobs_multi,
    save_jobs_to_db,
    enrich_jobs_with_match
)

logger = logging.getLogger("Scheduler")
if not logger.handlers:
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(h)
logger.setLevel(logging.INFO)

USER_YEARS = 2
COMPANIES = ["zoho", "google", "microsoft", "amazon"]

# ---------- INTERNAL ASYNC RUNNER ----------

async def run_scraper(companies: list[str]):
    """
    Orchestrates scraping + enrichment + persistence.
    Wrapped by job_scraper_task() which handles the loop.
    """
    logger.info(f"[RUN] Starting scrape for companies={companies}")
    try:
        jobs = await scrape_jobs_multi(companies, role="developer", location="Bangalore")
    except Exception as e:
        logger.exception(f"[FATAL] scrape_jobs_multi crashed: {e}")
        return

    # Filter out clearly invalid rows early (title / apply_url missing)
    valid_jobs = [j for j in jobs if j.get("title") and j.get("apply_url")]
    dropped = len(jobs) - len(valid_jobs)
    if dropped:
        logger.warning(f"[CLEAN] Dropped {dropped} invalid job records (missing title/apply_url)")

    # Enrich (only if not already done inside scrape_jobs_multi)
    try:
        enrich_jobs_with_match(valid_jobs, USER_YEARS)
    except Exception as e:
        logger.exception(f"[ERROR] Enrichment failed: {e}")

    # Persist
    try:
        save_jobs_to_db(valid_jobs)
        logger.info(f"[DB] Saved/Upserted {len(valid_jobs)} jobs.")
    except Exception as e:
        logger.exception(f"[ERROR] Saving jobs failed: {e}")

    logger.info(f"[DONE] Scrape cycle ended. Total raw={len(jobs)} stored={len(valid_jobs)}")


# ---------- SCHEDULER JOB WRAPPER ----------

def job_scraper_task():
    """
    Runs in APScheduler thread; creates its own event loop safely.
    Any exception is caught & logged so the scheduler keeps running.
    """
    start_ts = datetime.utcnow()
    logger.info("==============================================")
    logger.info(f"[TASK] Scheduled scrape started at {start_ts.isoformat()}Z")
    logger.info(f"[TASK] Companies: {COMPANIES}")

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_scraper(COMPANIES))
    except Exception as e:
        logger.exception(f"[TASK-ERROR] job_scraper_task failed: {e}")
    finally:
        try:
            if not loop.is_closed():
                loop.close()
        except Exception:
            pass
        logger.info("[TASK] Scheduled scrape finished.")
        logger.info("==============================================")


# ---------- OPTIONAL LISTENERS (LOG SUCCESS/FAIL) ----------

def _job_listener(event):
    if event.exception:
        logger.error(f"[APSCHED] Job {event.job_id} raised an exception.")
    else:
        logger.info(f"[APSCHED] Job {event.job_id} executed successfully.")


# ---------- START / STOP SCHEDULER ----------

_scheduler: BackgroundScheduler | None = None

def start_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        logger.info("[APSCHED] Scheduler already running; skipping start.")
        return

    _scheduler = BackgroundScheduler()
    # Midnight daily run
    _scheduler.add_job(job_scraper_task, "cron", hour=0, minute=0, id="daily_midnight_scrape")

    _scheduler.add_listener(_job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)
    _scheduler.start()
    logger.info("[APSCHED] Scheduler started with jobs: %s", _scheduler.get_jobs())


def shutdown_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        logger.info("[APSCHED] Shutting down scheduler...")
        _scheduler.shutdown(wait=False)
        logger.info("[APSCHED] Scheduler shut down.")


# ---------- OPTIONAL: AUTO START ON IMPORT (if desired) ----------
# Call start_scheduler() explicitly from app startup instead of here
# to avoid multiple instances when using reload.
