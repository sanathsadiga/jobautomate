from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.api import health, resume, jobs
from app.scheduler import start_scheduler, shutdown_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    start_scheduler()
    print("[LIFESPAN] Scheduler started.")
    
    yield  # App runs while we're in this context

    # Shutdown
    shutdown_scheduler()
    print("[LIFESPAN] Scheduler stopped.")

app = FastAPI(title="Job AutoApply Backend", lifespan=lifespan)

# Include routes
app.include_router(health.router)
app.include_router(resume.router)
app.include_router(jobs.router)
