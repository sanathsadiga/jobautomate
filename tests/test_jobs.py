import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_search_jobs_with_valid_role():
    payload = {"companies": ["zoho"], "role": "developer", "location": ""}
    resp = client.post("/jobs/search", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert isinstance(data["results"], list)
    # Optional: ensure at least one job has expected company name
    assert any(j.get("company") == "Zoho" for j in data["results"])


def test_search_jobs_with_invalid_company():
    payload = {"companies": ["invalid"], "role": "developer", "location": ""}
    resp = client.post("/jobs/search", json=payload)
    assert resp.status_code == 200  # Should succeed logically, returning error inside results
    data = resp.json()
    assert "results" in data
    assert len(data["results"]) == 1
    job = data["results"][0]
    assert job["company"] == "invalid"
    assert "error" in job


def test_search_jobs_without_filters():
    payload = {"companies": ["zoho"], "role": "", "location": ""}
    resp = client.post("/jobs/search", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"results": [{"note": "Please provide role or location"}]}

def test_search_jobs_multiple_companies():
    payload = {
        "companies": ["google", "zoho", "microsoft", "amazon"],
        "role": "developer",
        "location": "Bangalore"
    }
    resp = client.post("/jobs/search", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    companies = {job["company"] for job in data["results"]}
    assert {"Google", "Zoho", "Microsoft", "Amazon"} <= companies

