import logging
import json
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional

# Module logger (shared format with other scrapers)
logger = logging.getLogger("ZohoScraper")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)  # Switch to DEBUG for verbose logs


def scrape_zoho_jobs(role: str, location: str) -> List[Dict[str, Any]]:
    """
    Scrape Zoho jobs. Filters by `role` substring in title and `location` substring in Country.
    Returns a list of normalized job dicts or note/error dicts.
    """
    url = "https://careers.zohocorp.com/jobs"
    role_filter = (role or "").strip().lower()
    location_filter = (location or "").strip().lower()

    logger.info(f"Starting Zoho scraper (role='{role_filter or '*'}', location='{location_filter or '*'}').")

    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=25,
        )
    except requests.RequestException as rexc:
        logger.error(f"Network error requesting Zoho jobs: {rexc}", exc_info=False)
        return [{"error": "Network error fetching Zoho jobs", "detail": str(rexc)}]

    if resp.status_code != 200:
        logger.warning(f"Unexpected Zoho status code {resp.status_code}")
        return [{"error": f"Failed to fetch Zoho jobs. Status code: {resp.status_code}"}]

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as parse_exc:
        logger.error(f"HTML parse failure for Zoho page: {parse_exc}", exc_info=False)
        return [{"error": "Failed to parse Zoho jobs HTML", "detail": str(parse_exc)}]

    job_input = soup.find("input", {"id": "jobs"})
    if not job_input:
        logger.warning("Hidden jobs input <input id='jobs'> not found on Zoho page.")
        return [{"error": "No job data element found on Zoho page."}]

    raw_value = job_input.get("value")
    if not raw_value:
        logger.warning("Jobs input has no value attribute.")
        return [{"error": "No job data value found on Zoho page."}]

    try:
        jobs_data = json.loads(raw_value)
    except json.JSONDecodeError as jerr:
        logger.error(f"JSON decode error for Zoho jobs blob: {jerr}", exc_info=False)
        return [{"error": "Corrupt job data JSON from Zoho", "detail": str(jerr)}]

    logger.info(f"Loaded {len(jobs_data)} raw Zoho job entries.")

    matched: List[Dict[str, Any]] = []
    for idx, job in enumerate(jobs_data, start=1):
        title: str = job.get("Posting_Title", "") or ""
        country: str = job.get("Country1", "") or ""
        title_l = title.lower()
        country_l = country.lower()

        # Role filter
        if role_filter and role_filter not in title_l:
            continue
        # Location filter
        if location_filter and location_filter not in country_l:
            continue

        job_id = job.get("id")
        apply_url = f"https://careers.zohocorp.com/jobs/Careers/{job_id}" if job_id else ""

        description_raw: Optional[str] = job.get("Job_Description", "")
        description_trimmed = (description_raw or "").strip()
        if len(description_trimmed) > 200:
            description_trimmed = description_trimmed[:200] + "..."

        job_obj = {
            "title": title.strip(),
            "location": country.strip(),
            "description": description_trimmed,
            "apply_url": apply_url
        }
        matched.append(job_obj)

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Matched Zoho job #{idx}: {title[:70]} | {country}")

    if not matched:
        logger.info("No Zoho jobs matched filters.")
        return [{"note": "No jobs matched the filter"}]

    logger.info(f"Zoho scraper completed. Matched jobs: {len(matched)}")
    return matched
