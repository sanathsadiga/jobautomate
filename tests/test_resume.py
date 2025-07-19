from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_upload_resume_pdf():
    with open("tests/Sanath_Resume (1).pdf", "rb") as f:
        response = client.post("/upload-resume", files={"file": ("resume.pdf", f, "application/pdf")})
        assert response.status_code == 200
        data = response.json()["parsed_data"]
        assert "name" in data
        assert "email" in data
        assert "skills" in data
