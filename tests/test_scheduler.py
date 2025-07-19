import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from apscheduler.schedulers.background import BackgroundScheduler

from app.scheduler import start_scheduler, job_scraper_task
from app.main import app


def test_scheduler_jobs():
    start_scheduler()  # No argument
    from app.scheduler import _scheduler
    jobs = _scheduler.get_jobs()
    assert len(jobs) > 0


def test_app_startup_shutdown():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_job_scraper_task():
    with patch("app.scheduler.run_scraper", return_value=None) as mock_run:
        job_scraper_task()
        mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_run_scraper():
    with patch("app.scheduler.scrape_jobs_multi", new_callable=AsyncMock, return_value=[{"title": "Test Job", "apply_url": "url"}]) as mock_scraper:
        from app.scheduler import run_scraper
        await run_scraper(["zoho"])
        mock_scraper.assert_called_once()
