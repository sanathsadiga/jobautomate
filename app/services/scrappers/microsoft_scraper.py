import time
import os
import logging
import contextlib
import requests
from typing import List, Dict, Any, Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import html
import tempfile
import random


# Fix cache directory issue
os.makedirs("/tmp/.cache/selenium", exist_ok=True)
os.environ["XDG_CACHE_HOME"] = "/tmp/.cache"

# ----------------------------------
# Normalization map
# ----------------------------------
NORMALIZE_REPLACEMENTS = {
    '’': "'",
    '‘': "'",
    '“': '"',
    '”': '"',
    '–': '-',
    '—': '-',
    '\u00a0': ' ',
    '\u200b': '',
}

# ----------------------------------
# Logger
# ----------------------------------
logger = logging.getLogger("MicrosoftScraper")
if not logger.handlers:
    h = logging.StreamHandler()
    f = logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
                          "%Y-%m-%d %H:%M:%S")
    h.setFormatter(f)
    logger.addHandler(h)
logger.setLevel(logging.INFO)


# ----------------------------------
# Public entry point
# ----------------------------------
def scrape_microsoft_jobs(role: str,
                          location: str,
                          deep: bool = True,
                          per_page: int = 20,
                          max_detail: int = 30) -> List[Dict[str, Any]]:
    """
    Scrape Microsoft Careers search page with Selenium for metadata
    and optionally enrich each job via MS detail API.
    """
    base_search = "https://jobs.careers.microsoft.com/global/en/search"
    url = f"{base_search}?q={role}&l={location}&pg=1&pgSz={per_page}&o=Relevance&flt=true"

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-logging")
    options.add_argument("--log-level=3")
    options.add_argument(f"--user-data-dir={tempfile.mkdtemp()}")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])
    options.add_argument(f"--remote-debugging-port={random.randint(9222, 9999)}")

    service = Service(log_path=os.devnull)

    logger.info(f"Starting Microsoft scraper (role='{role}', location='{location}', deep={deep})")

    driver = None
    jobs: List[Dict[str, Any]] = []

    try:
        with open(os.devnull, "w") as f, contextlib.redirect_stderr(f):
            driver = webdriver.Chrome(service=service, options=options)

        logger.info(f"Navigating search: {url}")
        driver.get(url)

        WebDriverWait(driver, 30).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div[role='listitem']"))
        )

        # Scroll a few times to ensure dynamic load
        for _ in range(4):
            driver.execute_script("window.scrollBy(0, 1500);")
            time.sleep(1.2)

        cards = driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']")
        logger.info(f"Search page job cards: {len(cards)}")

        for idx, card in enumerate(cards, start=1):
            try:
                title_el = card.find_element(By.CSS_SELECTOR, "h2")
                title = title_el.text.strip()

                try:
                    snippet_el = card.find_element(By.CSS_SELECTOR, "span[aria-label='job description']")
                    snippet = snippet_el.text.strip()
                except Exception:
                    snippet = ""

                job_id = _extract_job_id_from_card(card)
                if not job_id:
                    logger.debug(f"Card #{idx}: no job_id found; skipping.")
                    continue

                formatted_title = re.sub(r'[^A-Za-z0-9 ]', '', title).strip()
                formatted_title = re.sub(r'\s+', ' ', formatted_title).replace(" ", "-")
                apply_url = f"https://jobs.careers.microsoft.com/global/en/job/{job_id}/{formatted_title}"

                job_obj = {
                    "company": "Microsoft",
                    "title": title,
                    "location": _extract_card_location(card),
                    "description": snippet[:200] + ("..." if len(snippet) > 200 else ""),
                    "apply_url": apply_url
                }
                jobs.append(job_obj)
            except Exception as e:
                logger.warning(f"Failed parsing search card #{idx}: {e}", exc_info=False)
                continue

        logger.info(f"Collected metadata for {len(jobs)} jobs.")

        if deep and jobs:
            _enrich_ms_jobs_with_full_description(jobs, max_detail=max_detail)

        logger.info(f"Microsoft scraper completed (deep={deep}). Final jobs: {len(jobs)}")
        return jobs

    except Exception as e:
        logger.error(f"Microsoft scraping failed: {e}", exc_info=False)
        return [{"error": "Exception occurred", "detail": str(e)}]

    finally:
        if driver:
            with contextlib.suppress(Exception):
                driver.quit()
                logger.info("Closed Microsoft Selenium driver.")


# ----------------------------------
# Helpers: search card parsing
# ----------------------------------
def _extract_job_id_from_card(card) -> Optional[str]:
    for el in card.find_elements(By.CSS_SELECTOR, "[aria-label]"):
        aria = el.get_attribute("aria-label") or ""
        if "Job item" in aria:
            # Extract first integer token
            for token in aria.split():
                if token.isdigit():
                    return token
    return None


def _extract_card_location(card) -> str:
    try:
        spans = card.find_elements(By.TAG_NAME, "span")
        loc_candidates = [s.text.strip() for s in spans if s.text and len(s.text) < 60]
        for c in loc_candidates:
            if any(tok in c.lower()
                   for tok in ("india", "hyderabad", "bangalore", "bengaluru", "noida",
                               "gurgaon", "pune", "chennai", "delhi")):
                return c
        return loc_candidates[0] if loc_candidates else ""
    except Exception:
        return ""


# ----------------------------------
# Enrichment (API for each job)
# ----------------------------------
def _enrich_ms_jobs_with_full_description(jobs: List[Dict[str, Any]], max_detail: int = 30):
    """
    Enrich up to max_detail jobs (or length of jobs) via Microsoft Job Detail API.
    Adds overview (description), qualifications, responsibilities, and experience fields.
    """
    detail_count = min(len(jobs), max_detail)
    logger.info(f"Enriching {detail_count} Microsoft jobs via detail API.")

    session = requests.Session()
    headers = {"User-Agent": "Mozilla/5.0"}

    USER_YEARS = 2  # Placeholder user experience (years)

    for idx in range(detail_count):
        job = jobs[idx]
        job_id = _extract_job_id_from_url(job.get("apply_url", "") or "")
        if not job_id:
            logger.debug(f"[Enrich] Job #{idx+1}: no job_id parsed from URL; skipping.")
            continue

        api_url = f"https://gcsservices.careers.microsoft.com/search/api/v1/job/{job_id}?lang=en_us"
        try:
            resp = session.get(api_url, headers=headers, timeout=20)
        except Exception as e:
            logger.debug(f"[Enrich] Job {job_id} API request error: {e}")
            continue

            # (We keep earlier logic)
        if resp.status_code != 200:
            logger.debug(f"[Enrich] Job {job_id} API status {resp.status_code}")
            continue

        try:
            data = resp.json()
        except Exception:
            logger.debug(f"[Enrich] Job {job_id} invalid JSON")
            continue

        detail = data.get("operationResult", {}).get("result", data)
        raw_desc = detail.get("description", "") or ""
        raw_qual = detail.get("qualifications", "") or ""
        raw_resp = detail.get("responsibilities", "") or ""

        clean_desc = _strip_html(raw_desc, limit=2000)
        clean_qual = _strip_html(raw_qual, limit=2000)
        clean_resp = _strip_html(raw_resp, limit=2000)

        # Combine for experience extraction (you can narrow to qualifications only)
        combined_text = " ".join(part for part in (clean_desc, clean_qual, clean_resp) if part)

        exp_min, exp_max, candidates = _extract_experience_numbers(combined_text)

        # Force assign if candidates exist (prevents null)
        if candidates:
            if exp_min is None:
                exp_min = candidates[0]
            if exp_max is None and len(candidates) > 1:
                exp_max = candidates[-1]

        # Determine match and reason
        is_match = True
        if exp_min is None:
            match_reason = "No explicit experience requirement found"
        else:
            if exp_min > USER_YEARS:
                is_match = False
                if exp_max and exp_max != exp_min:
                    match_reason = f"Requires {exp_min}-{exp_max} yrs (min {exp_min} > user {USER_YEARS})"
                else:
                    match_reason = f"Requires {exp_min}+ yrs (user {USER_YEARS})"
            else:
                if exp_max and exp_max != exp_min:
                    match_reason = f"User meets range {exp_min}-{exp_max} yrs"
                else:
                    match_reason = f"User meets minimum {exp_min} yrs"

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                f"[Enrich] job_id={job_id} candidates={candidates} exp_min={exp_min} exp_max={exp_max} match={is_match}"
            )

        job.update({
            "overview": clean_desc[:500] + ("..." if len(clean_desc) > 500 else ""),
            "qualifications": clean_qual[:500] + ("..." if len(clean_qual) > 500 else ""),
            "responsibilities": clean_resp[:500] + ("..." if len(clean_resp) > 500 else ""),
            "experience_min": exp_min,
            "experience_max": exp_max,
            "experience_candidates": candidates,  # keep for verification; remove later
            "match": is_match,
            "match_reason": match_reason
        })

    logger.info("Enrichment complete.")


# ----------------------------------
# Experience extraction
# ----------------------------------
def _extract_experience_numbers(text: str):
    """
    Returns (exp_min, exp_max, sorted_candidates).
    This is robust and *will not* return candidates without also being able to derive min.
    """
    if not text:
        return None, None, []

    # Normalize
    for k, v in NORMALIZE_REPLACEMENTS.items():
        text = text.replace(k, v)
    text = text.replace("\\u002B", "+").replace("\u002B", "+")

    # Patterns
    range_re = re.compile(r'(?<!\d)(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:\+?\s*)?(?:years?|yrs?)', re.I)
    single_re = re.compile(
        r'(?:(?:at\s+least|min(?:imum)?(?:\s+of)?|minimum|required|over|more than)\s*)?'
        r'(\d{1,2})\s*\+?\s*(?:years?|yrs?)',
        re.I
    )

    nums = set()

    for m in range_re.finditer(text):
        a = int(m.group(1))
        b = int(m.group(2))
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


# ----------------------------------
# Utilities
# ----------------------------------
def _extract_job_id_from_url(url: str) -> Optional[str]:
    m = re.search(r'/job/(\d+)/', url)
    return m.group(1) if m else None


def _strip_html(fragment: str, limit: int = None) -> str:
    if not fragment:
        return ""
    txt = html.unescape(fragment)
    txt = txt.replace("\\u002B", "+").replace("\u002B", "+")
    txt = re.sub(r'<[^>]+>', ' ', txt)
    txt = re.sub(r'\s+', ' ', txt).strip()
    if limit and len(txt) > limit:
        return txt[:limit].rstrip() + "..."
    return txt
