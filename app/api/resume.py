from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.resume_parser import extract_resume_data

router = APIRouter()

@router.post("/upload-resume", tags=["Resume"])
async def upload_resume(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    contents = await file.read()
    data = extract_resume_data(contents)
    return {"parsed_data": data}
