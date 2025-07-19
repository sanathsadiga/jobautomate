import re
from typing import Optional, Tuple, Dict, Any, List

RANGE_RE      = re.compile(r'(\d+)\s*[-–]\s*(\d+)\s*(?:\+?\s*)?(?:years?|yrs?)', re.I)
SINGLE_RE     = re.compile(r'(?:at\s+least|min(?:imum)?(?:\s+of)?|minimum|required|over|more than)?\s*(\d+)\+?\s*(?:years?|yrs?)', re.I)
OR_MORE_RE    = re.compile(r'(\d+)\s*(?:\+|\bor more\b)\s*(?:years?|yrs?)', re.I)
UP_TO_RE      = re.compile(r'(?:up to|upto)\s*(\d+)\s*(?:years?|yrs?)', re.I)
ENTRY_LEVEL_RE= re.compile(r'\b(entry[- ]level|fresher|graduate|intern(ship)?|junior)\b', re.I)
SENIORITY_RE  = re.compile(r'\b(senior|sr\.?|staff|principal|lead)\b', re.I)

def _extract_experience(text: str) -> Tuple[Optional[int], Optional[int], Dict[str, Any]]:
    """
    Return (min_years, max_years, flags)
    """
    flags = {
        "entry_level": False,
        "senior": False
    }
    if not text:
        return None, None, flags

    # Entry-level keywords
    if ENTRY_LEVEL_RE.search(text):
        flags["entry_level"] = True

    # Range first
    m = RANGE_RE.search(text)
    if m:
        mn = int(m.group(1))
        mx = int(m.group(2))
        return mn, mx, flags

    # Or-more
    m = OR_MORE_RE.search(text)
    if m:
        n = int(m.group(1))
        return n, None, flags

    # Single
    m = SINGLE_RE.search(text)
    if m:
        n = int(m.group(1))
        return n, None, flags

    # Up to
    m = UP_TO_RE.search(text)
    if m:
        # "up to 2 years" -> min 0, max N
        n = int(m.group(1))
        return 0, n, flags

    # Seniority detection (only if no numeric)
    if SENIORITY_RE.search(text):
        flags["senior"] = True

    return None, None, flags

def enrich_jobs_with_match(jobs: List[Dict[str, Any]], user_years: int) -> List[Dict[str, Any]]:
    """
    Adds experience_min, experience_max, match, match_reason to each job.
    """
    for job in jobs:
        text_blob = " ".join([
            job.get("title", ""),
            job.get("description", "")
        ])
        exp_min, exp_max, flags = _extract_experience(text_blob)

        # Decision
        if flags["entry_level"]:
            match = user_years >= 0  # always true
            reason = "Entry-level / fresher role"
        elif exp_min is not None and exp_min > user_years:
            match = False
            reason = f"Requires {exp_min}+ years; user has {user_years}"
        elif flags["senior"] and exp_min is None and user_years <= 2:
            match = False
            reason = "Senior-level keywords detected"
        else:
            match = True
            if exp_min is not None:
                if exp_max:
                    reason = f"Matches range {exp_min}-{exp_max} years"
                else:
                    reason = f"Minimum {exp_min} years – OK"
            else:
                reason = "No explicit experience requirement found"

        job["experience_min"] = exp_min
        job["experience_max"] = exp_max
        job["match"] = match
        job["match_reason"] = reason

    return jobs
