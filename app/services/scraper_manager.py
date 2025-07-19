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
async def scrape_company(company, role, location):
    if company.lower() == "zoho":
        jobs = scrape_zoho_jobs(role, location)  # Zoho uses requests (sync)
        return [{"company": "Zoho", **job} for job in jobs]

    elif company.lower() == "google":
        jobs = scrape_google_jobs(role, location)  # Sync or async?
        return [{"company": "Google", **job} for job in jobs]

    elif company.lower() == "microsoft":
        jobs = scrape_microsoft_jobs(role, location)  # ✅ Use await here
        save_jobs_to_db(jobs)
        return jobs
    
    elif company == "amazon":
        print("Scraping Amazon...")
        jobs = await scrape_amazon_jobs(role, location)
        print(f"Amazon Scraper Returned: {len(jobs)} jobs")
        save_jobs_to_db(jobs)
        return [{"company": "Amazon", **job} for job in jobs]


    return [{"company": company, "error": "Scraper not implemented"}]

async def scrape_jobs_multi(companies, role, location):
    tasks = [scrape_company(c.lower(), role, location) for c in companies]
    results = await asyncio.gather(*tasks)
    combined = [job for company_jobs in results for job in company_jobs]
    real_jobs = [j for j in combined if "title" in j]
    enrich_jobs_with_match(real_jobs, USER_YEARS)
    save_jobs_to_db(real_jobs)
    return combined

def save_jobs_to_db(jobs):
    db = SessionLocal()
    try:
        for job in jobs:
            # Skip records with missing required fields
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
                index_elements=['apply_url'],  # upsert based on apply_url
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
