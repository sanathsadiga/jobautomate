import asyncio
import logging
import tempfile
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random
import uuid
import os

# Fix cache directory issue
os.makedirs("/tmp/.cache/selenium", exist_ok=True)
os.environ["XDG_CACHE_HOME"] = "/tmp/.cache"


# Configure logger for this module
logger = logging.getLogger("AmazonScraper")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)  # Change to DEBUG for verbose logs


async def scrape_amazon_jobs(role: str, location: str = None) -> list:
    """
    Scrapes Amazon job postings for the given role.
    Location is ignored (Amazon search URL is keyword-based).
    """
    url = f"https://www.amazon.jobs/en/search?keywords={role}"

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    unique_user_data_dir = os.path.join(tempfile.gettempdir(), f"selenium-{uuid.uuid4()}")
    options.add_argument(f"--user-data-dir={unique_user_data_dir}")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])  # Suppress DevTools logs
    options.add_argument(f"--remote-debugging-port={random.randint(9222, 9999)}")


    def run_selenium():
        jobs = []
        logger.info(f"Starting Amazon scraper for role: '{role}'")

        driver = webdriver.Chrome(options=options)
        try:
            logger.info(f"Navigating to {url}")
            driver.get(url)

            logger.debug("Waiting for job cards to load...")
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "div.job-tile"))
            )

            job_cards = driver.find_elements(By.CSS_SELECTOR, "div.job-tile")
            logger.info(f"Found {len(job_cards)} job cards on Amazon")

            for idx, card in enumerate(job_cards, start=1):
                try:
                    title_elem = card.find_element(By.CSS_SELECTOR, "h3.job-title")
                    title = title_elem.text.strip() if title_elem else "No Title"

                    try:
                        location_elem = card.find_element(By.CSS_SELECTOR, ".job-location")
                        job_location = location_elem.text.strip()
                    except Exception:
                        job_location = ""  # fallback if location not present

                    link_elem = card.find_element(By.CSS_SELECTOR, "a.job-link")
                    apply_url = link_elem.get_attribute("href") if link_elem else ""

                    job_data = {
                        "company": "Amazon",
                        "title": title,
                        "location": job_location,
                        "description": "",
                        "apply_url": apply_url,
                    }
                    jobs.append(job_data)

                    logger.debug(f"Parsed job #{idx}: {title} - {job_location}")
                except Exception as e:
                    logger.warning(f"Error parsing job card #{idx}: {e}", exc_info=False)
                    continue
        finally:
            driver.quit()
            logger.info("Closed Amazon Selenium driver.")
            logger.info(f"Amazon scraper completed. Total jobs: {len(jobs)}")

        return jobs

    return await asyncio.to_thread(run_selenium)
