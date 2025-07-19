from fastapi import APIRouter,Query
from app.models.jobs import JobSearchRequest
from app.services.scraper_manager import scrape_jobs_multi
from app.services.zoho_opener import open_zoho_job_page
from typing import List, Optional
from pydantic import BaseModel
from rapidfuzz import fuzz
from fastapi import APIRouter
from app.database import SessionLocal
from app.models.jobs import Job


router = APIRouter()

# ✅ Use this Pydantic model for request body
class MultiJobSearchRequest(BaseModel):
    companies: List[str]
    role: Optional[str] = None
    location: Optional[str] = None

@router.post("/jobs/search", tags=["Jobs"])
async def search_multi_jobs(request: MultiJobSearchRequest):
    if not request.role and not request.location:
        return {"results": [{"note": "Please provide role or location"}]}
    
    results = await scrape_jobs_multi(request.companies, request.role or "", request.location or "")
    
    return {"results": results if results else [{"note": "No jobs found"}]}

@router.get("/jobs", tags=["Jobs"])
def get_jobs():
    db = SessionLocal()
    jobs = db.query(Job).order_by(Job.created_at.desc()).all()
    db.close()
    return {"results": [j.__dict__ for j in jobs]}

@router.post("/jobs/open")
def upload_resume():
    job_url = "https://careers.zohocorp.com/jobs/Careers/2803000614929615"
    resume_path = r"C:\Users\sanat\OneDrive\Desktop\JobAppportal\backend\tests\Sanath_Resume (1).pdf"
    return open_zoho_job_page(job_url, resume_path)

