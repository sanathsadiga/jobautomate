import pdfplumber
import io
import re

def extract_resume_data(file_bytes: bytes) -> dict:
    text = ""
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"

    # Very basic pattern matching (can be improved later)
    name = text.split('\n')[0].strip()[:50]  # First line, assume it's name
    email = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    phone = re.findall(r"(\+?\d{10,13})", text)
    
    # Keyword match for skills
    known_skills = ["python", "fastapi", "django", "node.js", "react", "aws", "sql", "mongodb"]
    skills = [skill for skill in known_skills if skill.lower() in text.lower()]

    return {
        "name": name,
        "email": email[0] if email else "",
        "phone": phone[0] if phone else "",
        "skills": skills
    }
