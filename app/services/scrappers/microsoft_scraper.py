import asyncio
import contextlib
import html
import logging
import os
import random
import re
import shutil
import tempfile
import time
import uuid
from typing import Any, Dict, List, Optional

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

try:
    from app.services.scrappers.selenium_utils import SELENIUM_START_LOCK
except Exception:
    SELENIUM_START_LOCK = None

logger = logging.getLogger("MicrosoftScraper")
if not logger.handlers:
    _h = logging.StreamHandler()
    _f = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    _h.setFormatter(_f)
    logger.addHandler(_h)
logger.setLevel(logging.INFO)

NORMALIZE_REPLACEMENTS = {
    "’": "'",
    "‘": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": "-",
    "\u00a0": " ",
    "\u200b": "",
}

USER_YEARS = 2  # adjust / externalize later


def _prepare_env():
    os.environ.setdefault("HOME", "/tmp")
    base_cache = "/tmp/.cache"
    os.makedirs(f"{base_cache}/selenium", exist_ok=True)
    os.environ["XDG_CACHE_HOME"] = base_cache

    now = time.time()
    for name in os.listdir("/tmp"):
        if name.startswith(("chrome-profile-", "selenium-tmp-")):
            path = os.path.join("/tmp", name)
            try:
                if now - os.path.getmtime(path) > 600:
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
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument(f"--remote-debugging-port={random.randint(9222, 9999)}")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    return options


def _create_driver_with_retry(options: Options, retries: int = 3, delay: float = 2.0):
    last_exc = None
    service = Service(log_path=os.devnull)
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"[Chrome] Launch attempt {attempt}/{retries}")
            driver = webdriver.Chrome(service=service, options=options)
            return driver
        except Exception as e:
            last_exc = e
            logger.warning(f"[Chrome] Launch failed attempt {attempt}: {e}")
            shutil.rmtree("/tmp/.org.chromium.Chromium", ignore_errors=True)
            time.sleep(delay)
    raise last_exc


def _extract_job_id_from_card(card) -> Optional[str]:
    for el in card.find_elements(By.CSS_SELECTOR, "[aria-label]"):
        aria = el.get_attribute("aria-label") or ""
        if "Job item" in aria:
            for token in aria.split():
                if token.isdigit():
                    return token
    return None


def _extract_card_location(card) -> str:
    try:
        spans = card.find_elements(By.TAG_NAME, "span")
        loc_candidates = [s.text.strip() for s in spans if s.text and len(s.text) < 60]
        for c in loc_candidates:
            if any(
                tok in c.lower()
                for tok in (
                    "india",
                    "hyderabad",
                    "bangalore",
                    "bengaluru",
                    "noida",
                    "gurgaon",
                    "pune",
                    "chennai",
                    "delhi",
                )
            ):
                return c
        return loc_candidates[0] if loc_candidates else ""
    except Exception:
        return ""


def _strip_html(fragment: str, limit: int = None) -> str:
    if not fragment:
        return ""
    txt = html.unescape(fragment)
    txt = txt.replace("\\u002B", "+").replace("\u002B", "+")
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    if limit and len(txt) > limit:
        return txt[:limit].rstrip() + "..."
    return txt


def _extract_job_id_from_url(url: str) -> Optional[str]:
    m = re.search(r"/job/(\d+)/", url)
    return m.group(1) if m else None


def _extract_experience_numbers(text: str):
    if not text:
        return None, None, []
    for k, v in NORMALIZE_REPLACEMENTS.items():
        text = text.replace(k, v)
    text = text.replace("\\u002B", "+").replace("\u002B", "+")

    range_re = re.compile(
        r"(?<!\d)(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:\+?\s*)?(?:years?|yrs?)", re.I
    )
    single_re = re.compile(
        r"(?:"
        r"(?:at\s+least|min(?:imum)?(?:\s+of)?|minimum|required|over|more than)\s*"
        r")?(\d{1,2})\s*\+?\s*(?:years?|yrs?)",
        re.I,
    )

    nums = set()
    for m in range_re.finditer(text):
        a, b = int(m.group(1)), int(m.group(2))
        if 0 < a <= 60:
            nums.add(a)
        if 0 < b <= 60:
            nums.add(b)
    for m in single_re.finditer(text):
        n = int(m.group(1))
        if 0 < n <= 60:
            nums.add(n)

    if not nums:
        return None, None, []
    ordered = sorted(nums)
    exp_min = ordered[0]
    exp_max = ordered[-1] if len(ordered) > 1 and ordered[-1] != exp_min else None
    return exp_min, exp_max, ordered


def _enrich_ms_jobs_with_full_description(jobs: List[Dict[str, Any]], max_detail: int):
    detail_count = min(len(jobs), max_detail)
    logger.info(f"Enriching {detail_count} Microsoft jobs via detail API.")

    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0"}

    for idx in range(detail_count):
        job = jobs[idx]
        job_id = _extract_job_id_from_url(job.get("apply_url", "") or "")
        if not job_id:
            continue
        api_url = f"https://gcsservices.careers.microsoft.com/search/api/v1/job/{job_id}?lang=en_us"
        try:
            resp = session.get(api_url, headers=headers, timeout=20)
        except Exception:
            continue
        if resp.status_code != 200:
            continue
        try:
            data = resp.json()
        except Exception:
            continue

        detail = data.get("operationResult", {}).get("result", data)
        raw_desc = detail.get("description") or ""
        raw_qual = detail.get("qualifications") or ""
        raw_resp = detail.get("responsibilities") or ""

        clean_desc = _strip_html(raw_desc, limit=2000)
        clean_qual = _strip_html(raw_qual, limit=2000)
        clean_resp = _strip_html(raw_resp, limit=2000)

        combined = " ".join([p for p in (clean_desc, clean_qual, clean_resp) if p])
        exp_min, exp_max, candidates = _extract_experience_numbers(combined)

        if candidates:
            if exp_min is None:
                exp_min = candidates[0]
            if exp_max is None and len(candidates) > 1:
                exp_max = candidates[-1]

        if exp_min is None:
            match = True
            reason = "No explicit experience requirement found"
        else:
            if exp_min > USER_YEARS:
                match = False
                if exp_max and exp_max != exp_min:
                    reason = f"Requires {exp_min}-{exp_max} yrs (user {USER_YEARS})"
                else:
                    reason = f"Requires {exp_min}+ yrs (user {USER_YEARS})"
            else:
                if exp_max and exp_max != exp_min:
                    reason = f"User meets range {exp_min}-{exp_max} yrs"
                else:
                    reason = f"User meets minimum {exp_min} yrs"

        job.update(
            {
                "overview": clean_desc[:500] + ("..." if len(clean_desc) > 500 else ""),
                "qualifications": clean_qual[:500]
                + ("..." if len(clean_qual) > 500 else ""),
                "responsibilities": clean_resp[:500]
                + ("..." if len(clean_resp) > 500 else ""),
                "experience_min": exp_min,
                "experience_max": exp_max,
                "match": match,
                "match_reason": reason,
            }
        )

    logger.info("Enrichment complete.")


def scrape_microsoft_jobs(
    role: str,
    location: str,
    deep: bool = True,
    per_page: int = 20,
    max_detail: int = 30,
) -> List[Dict[str, Any]]:
    _prepare_env()
    base_search = "https://jobs.careers.microsoft.com/global/en/search"
    url = f"{base_search}?q={role}&l={location}&pg=1&pgSz={per_page}&o=Relevance&flt=true"

    options = _build_chrome_options()

    driver = None
    jobs: List[Dict[str, Any]] = []

    try:
        driver = _create_driver_with_retry(options)
        logger.info(f"Navigating search: {url}")
        driver.get(url)

        WebDriverWait(driver, 35).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[role='listitem']"))
        )

        # gentle scroll to trigger lazy loads
        for _ in range(5):
            driver.execute_script("window.scrollBy(0, 1500);")
            time.sleep(1.0)

        cards = driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']")
        logger.info(f"Search page job cards: {len(cards)}")

        for idx, card in enumerate(cards, start=1):
            try:
                title_el = card.find_element(By.CSS_SELECTOR, "h2")
                title = title_el.text.strip()
                snippet = ""
                try:
                    snippet_el = card.find_element(
                        By.CSS_SELECTOR, "span[aria-label='job description']"
                    )
                    snippet = snippet_el.text.strip()
                except Exception:
                    pass

                job_id = _extract_job_id_from_card(card)
                if not job_id:
                    continue

                formatted = re.sub(r"[^A-Za-z0-9 ]", "", title).strip()
                formatted = re.sub(r"\s+", " ", formatted).replace(" ", "-")
                apply_url = (
                    f"https://jobs.careers.microsoft.com/global/en/job/{job_id}/{formatted}"
                )

                jobs.append(
                    {
                        "company": "Microsoft",
                        "title": title,
                        "location": _extract_card_location(card),
                        "description": snippet[:200]
                        + ("..." if len(snippet) > 200 else ""),
                        "apply_url": apply_url,
                    }
                )
            except Exception as e:
                logger.debug(f"Failed parsing card #{idx}: {e}")

        logger.info(f"Collected {len(jobs)} Microsoft job metadata items.")

        if deep and jobs:
            _enrich_ms_jobs_with_full_description(jobs, max_detail=max_detail)

        logger.info(f"Microsoft scraper completed (deep={deep}). Final: {len(jobs)}")
        return jobs

    except Exception as e:
        logger.error(f"Microsoft scraping failed: {e}")
        return [{"error": "Exception occurred", "detail": str(e), "company": "Microsoft"}]
    finally:
        if driver:
            with contextlib.suppress(Exception):
                driver.quit()


# Async wrapper if you decide to await it elsewhere
async def scrape_microsoft_jobs_async(role: str, location: str, **kwargs):
    # Optional lock for async usage
    if SELENIUM_START_LOCK:
        async with SELENIUM_START_LOCK:
            return await asyncio.to_thread(
                scrape_microsoft_jobs, role, location, **kwargs
            )
    return await asyncio.to_thread(scrape_microsoft_jobs, role, location, **kwargs)
