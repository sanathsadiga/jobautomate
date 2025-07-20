import asyncio
from app.services.scrappers.zoho_scraper import scrape_zoho_jobs
from app.services.scrappers.scraper_google import scrape_google_jobs
from app.services.scrappers.microsoft_scraper import scrape_microsoft_jobs
from app.services.scrappers.amazon_scraper import scrape_amazon_jobs
from app.services.enrichment import enrich_jobs_with_match
from app.database import SessionLocal
from app.models.jobs import Job
from sqlalchemy.dialects.postgresql import insert

USER_YEARS = 2
SELENIUM_COMPANIES = {"microsoft", "amazon"}  # Selenium-based scrapers


async def scrape_company(company, role, location):
    if company.lower() == "zoho":
        jobs = scrape_zoho_jobs(role, location)
        return [{"company": "Zoho", **job} for job in jobs]

    elif company.lower() == "google":
        jobs = scrape_google_jobs(role, location)
        return [{"company": "Google", **job} for job in jobs]

    # replace inside scraper_manager for microsoft part:
    elif company.lower() == "microsoft":
        from app.services.scrappers.microsoft_scraper import scrape_microsoft_jobs_async
        jobs = await scrape_microsoft_jobs_async(role, location)
        save_jobs_to_db(jobs)
        return jobs


    elif company.lower() == "amazon":
        print("Scraping Amazon...")
        jobs = await scrape_amazon_jobs(role, location)
        print(f"Amazon Scraper Returned: {len(jobs)} jobs")
        save_jobs_to_db(jobs)
        return jobs

    return [{"company": company, "error": "Scraper not implemented"}]


async def scrape_jobs_multi(companies, role, location):
    # 1. Non-Selenium scrapers (Zoho, Google) run in parallel
    non_selenium_tasks = [
        scrape_company(c, role, location)
        for c in companies if c.lower() not in SELENIUM_COMPANIES
    ]
    non_selenium_results = []
    if non_selenium_tasks:
        non_selenium_results = await asyncio.gather(*non_selenium_tasks)

    # 2. Selenium scrapers (Microsoft, Amazon) run sequentially
    selenium_results = []
    for c in companies:
        if c.lower() in SELENIUM_COMPANIES:
            try:
                result = await scrape_company(c, role, location)
                selenium_results.append(result)
            except Exception as e:
                print(f"[ERROR] {c} scraper failed: {e}")
                selenium_results.append([{"company": c, "error": str(e)}])

    # 3. Combine results
    results = non_selenium_results + selenium_results
    combined = [job for company_jobs in results for job in company_jobs]

    # 4. Enrichment & DB
    real_jobs = [j for j in combined if "title" in j]
    enrich_jobs_with_match(real_jobs, USER_YEARS)
    save_jobs_to_db(real_jobs)

    return combined


def save_jobs_to_db(jobs):
    db = SessionLocal()
    try:
        for job in jobs:
            if not job.get("title") or not job.get("apply_url"):
                print(f"[SKIP] Missing required fields: {job}")
                continue

            stmt = insert(Job).values(
                company=job.get("company", ""),
                title=job.get("title", ""),
                location=job.get("location", ""),
                description=job.get("description", ""),
                apply_url=job.get("apply_url", ""),
                experience_min=job.get("experience_min", 0),
                experience_max=job.get("experience_max", 0),
                match=job.get("match", False),
                match_reason=job.get("match_reason", "")
            ).on_conflict_do_update(
                index_elements=['apply_url'],
                set_={
                    'company': job.get("company", ""),
                    'title': job.get("title", ""),
                    'location': job.get("location", ""),
                    'description': job.get("description", ""),
                    'experience_min': job.get("experience_min", 0),
                    'experience_max': job.get("experience_max", 0),
                    'match': job.get("match", False),
                    'match_reason': job.get("match_reason", "")
                }
            ).returning(Job.id)

            result = db.execute(stmt)
            if result:
                print(f"[UPSERT] Job '{job.get('title')}' ({job.get('apply_url')}) updated/inserted.")

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[ERROR] save_jobs_to_db failed: {e}")
    finally:
        db.close()
