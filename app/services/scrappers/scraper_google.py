import logging
import requests
from typing import List, Dict, Any

# Logger setup
logger = logging.getLogger("GoogleScraper")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)  # Change to DEBUG for detailed logs


def scrape_google_jobs(role: str, location: str) -> List[Dict[str, Any]]:
    """
    Fetch job listings from Google's careers API.
    Filters by role and location if provided.
    Returns a list of normalized job dicts or a note/error dict.
    """
    url = "https://careers.google.com/api/v3/search/"
    params = {
        "q": role,
        "page": 1,
        "page_size": 20,
    }

    if location:
        params["location"] = location

    logger.info(f"Starting Google scraper (role='{role or '*'}', location='{location or '*'}').")
    logger.debug(f"Requesting {url} with params: {params}")

    try:
        response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    except requests.RequestException as req_err:
        logger.error(f"Network error fetching Google jobs: {req_err}", exc_info=False)
        return [{"error": "Network error fetching Google jobs", "detail": str(req_err)}]

    if response.status_code != 200:
        logger.warning(f"Google jobs fetch failed (status {response.status_code})")
        return [{"error": f"Google jobs fetch failed (status {response.status_code})"}]

    try:
        data = response.json()
    except Exception as json_err:
        logger.error(f"Failed to parse JSON from Google response: {json_err}", exc_info=False)
        return [{"error": "Invalid JSON from Google", "detail": str(json_err)}]

    if "jobs" not in data:
        logger.info("Google API returned no jobs key.")
        return [{"note": "No jobs found for given filters"}]

    jobs_list: List[Dict[str, Any]] = []
    for idx, job in enumerate(data.get("jobs", []), start=1):
        try:
            # Extract readable locations
            locs = [loc.get("display", "") for loc in job.get("locations", []) if isinstance(loc, dict)]
            location_str = ", ".join([loc for loc in locs if loc]) or "Not specified"

            description = job.get("descriptionSnippet", "") or ""
            if len(description) > 200:
                description = description[:200] + "..."

            job_obj = {
                "title": job.get("title", "No Title"),
                "location": location_str,
                "description": description,
                "apply_url": f"https://careers.google.com/jobs/results/{job.get('id')}/",
            }
            jobs_list.append(job_obj)

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Google job #{idx}: {job_obj['title']} | {job_obj['location']}")
        except Exception as job_parse_err:
            logger.warning(f"Error parsing Google job #{idx}: {job_parse_err}", exc_info=False)
            continue

    if not jobs_list:
        logger.info("No matching Google jobs found.")
        return [{"note": "No matching Google jobs found"}]

    logger.info(f"Google scraper completed. Matched jobs: {len(jobs_list)}")
    return jobs_list
