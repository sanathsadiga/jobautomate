import asyncio
import logging
import os
import random
import shutil
import tempfile
import time
import uuid
from typing import List

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# If you created the lock utility (recommended):
try:
    from app.services.scrappers.selenium_utils import SELENIUM_START_LOCK
except Exception:
    SELENIUM_START_LOCK = None  # fallback

logger = logging.getLogger("AmazonScraper")
if not logger.handlers:
    _h = logging.StreamHandler()
    _f = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    _h.setFormatter(_f)
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

# ---------- Internal Helpers ---------- #

def _prepare_env():
    """
    Make sure HOME / cache directories exist & are writable.
    """
    os.environ.setdefault("HOME", "/tmp")
    base_cache = "/tmp/.cache"
    selenium_cache = f"{base_cache}/selenium"
    os.makedirs(selenium_cache, exist_ok=True)
    os.environ["XDG_CACHE_HOME"] = base_cache

    # Clean *old* Chromium temp dirs occasionally (best effort)
    # Avoid deleting very recent ones to reduce race risk
    now = time.time()
    for name in os.listdir("/tmp"):
        if name.startswith(("chrome-profile-", "selenium-tmp-")):
            path = os.path.join("/tmp", name)
            try:
                if now - os.path.getmtime(path) > 600:  # older than 10 min
                    shutil.rmtree(path, ignore_errors=True)
            except Exception:
                pass


def _build_chrome_options() -> Options:
    profile_dir = os.path.join("/tmp", f"chrome-profile-{uuid.uuid4()}")
    os.makedirs(profile_dir, exist_ok=True)

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-features=OptimizationGuideModelDownloading")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument(f"--remote-debugging-port={random.randint(9222, 9999)}")
    # Cuts down noisy logs
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    return options


def _create_driver_with_retry(options: Options, retries: int = 3, delay: float = 2.0):
    """
    Robust Chrome startup with retry & cleanup.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"[Chrome] Launch attempt {attempt}/{retries}")
            driver = webdriver.Chrome(options=options)
            return driver
        except Exception as e:
            last_exc = e
            logger.warning(f"[Chrome] Launch failed attempt {attempt}: {e}")
            # Clean known temp directories
            shutil.rmtree("/tmp/.org.chromium.Chromium", ignore_errors=True)
            time.sleep(delay)
    raise last_exc


# ---------- Public Async API ---------- #

async def scrape_amazon_jobs(role: str, location: str = None) -> List[dict]:
    """
    Scrapes Amazon jobs for role (location ignored in current search URL).
    Always returns a list (possibly empty or with 'error' dict).
    """
    _prepare_env()
    url = f"https://www.amazon.jobs/en/search?keywords={role}"

    options = _build_chrome_options()

    async def _run() -> List[dict]:
        # Serialize startup if lock provided
        if SELENIUM_START_LOCK:
            async with SELENIUM_START_LOCK:
                driver = await asyncio.to_thread(_create_driver_with_retry, options)
        else:
            driver = await asyncio.to_thread(_create_driver_with_retry, options)

        jobs: List[dict] = []
        try:
            logger.info(f"Navigating: {url}")
            await asyncio.to_thread(driver.get, url)

            # Wait for job tiles (Amazon page structure may evolve)
            try:
                await asyncio.to_thread(
                    WebDriverWait(driver, 25).until,
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.job-tile")),
                )
            except Exception as e:
                logger.warning(f"No job tiles found (timeout?): {e}")

            cards = await asyncio.to_thread(
                driver.find_elements, By.CSS_SELECTOR, "div.job-tile"
            )
            logger.info(f"Amazon cards found: {len(cards)}")

            for idx, card in enumerate(cards, start=1):
                try:
                    title_el = card.find_element(By.CSS_SELECTOR, "h3.job-title")
                    title = title_el.text.strip() if title_el else "Untitled"

                    # location may be optional
                    try:
                        loc_el = card.find_element(By.CSS_SELECTOR, ".job-location")
                        loc = loc_el.text.strip()
                    except Exception:
                        loc = ""

                    link_el = card.find_element(By.CSS_SELECTOR, "a.job-link")
                    apply_url = link_el.get_attribute("href") if link_el else ""

                    if not apply_url:
                        continue

                    jobs.append(
                        {
                            "company": "Amazon",
                            "title": title,
                            "location": loc,
                            "description": "",
                            "apply_url": apply_url,
                        }
                    )
                except Exception as e:
                    logger.debug(f"Card parse error #{idx}: {e}")

            logger.info(f"Amazon scraper collected {len(jobs)} jobs.")
            return jobs
        except Exception as e:
            logger.error(f"Amazon scraping failed: {e}")
            return [{"error": "Exception occurred", "detail": str(e), "company": "Amazon"}]
        finally:
            try:
                await asyncio.to_thread(driver.quit)
            except Exception:
                pass

    return await _run()
