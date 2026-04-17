from __future__ import annotations
import re
import hashlib
from typing import List, Tuple
from src.models import Job


# Positive visa signals — any match → "explicit" or "possible"
VISA_POSITIVE_STRONG = re.compile(
    r"visa\s+sponsor(?:ship)?|"
    r"relocation\s+(?:assistance|support|package|provided)|"
    r"work\s+permit\s+(?:provided|supported|sponsored)|"
    r"sponsor(?:ing)?\s+(?:your\s+)?visa|"
    r"we\s+(?:do\s+)?sponsor|"
    r"blue\s+card|"
    r"skilled\s+worker\s+visa|"
    r"lmia\s+(?:approved|eligible|supported)|"
    r"ict\s+visa|"
    r"482\s+visa|"
    r"employment\s+pass|"
    r"sponsorship\s+(?:is\s+)?available|"
    r"visa\s+(?:and\s+)?relocation",
    re.IGNORECASE,
)

VISA_POSITIVE_WEAK = re.compile(
    r"open\s+to\s+relocation|"
    r"relocation\s+welcome|"
    r"international\s+(?:candidates|applicants)|"
    r"we\s+help\s+with\s+(?:visa|relocation)|"
    r"global\s+mobility|"
    r"work\s+authorization\s+support",
    re.IGNORECASE,
)

# Negative visa signals — any match → "negative"
VISA_NEGATIVE = re.compile(
    r"no\s+visa\s+sponsor(?:ship)?|"
    r"must\s+(?:already\s+)?have\s+(?:valid\s+)?work\s+(?:authoriz|permit)|"
    r"citizens?\s+(?:and\s+permanent\s+residents?\s+)?only|"
    r"(?:permanent\s+)?residents?\s+only|"
    r"pr\s+(?:holder|required|only)|"
    r"do\s+not\s+(?:offer|provide)\s+sponsorship|"
    r"unable\s+to\s+(?:offer|provide)\s+(?:visa\s+)?sponsor|"
    r"not\s+(?:able|in\s+a\s+position)\s+to\s+sponsor|"
    r"must\s+be\s+authorized\s+to\s+work\s+in|"
    r"no\s+relocation\s+(?:assistance|support)|"
    r"local\s+candidates?\s+only|"
    r"eu\s+(?:passport|citizen)\s+(?:required|only)",
    re.IGNORECASE,
)


def classify_visa(text: str) -> Tuple[str, List[str]]:
    """Return (status, matched_signals). Status: explicit | possible | negative | unknown."""
    signals = []

    if VISA_NEGATIVE.search(text):
        matches = VISA_NEGATIVE.findall(text)
        return "negative", [m.strip() for m in matches[:3]]

    strong = VISA_POSITIVE_STRONG.findall(text)
    if strong:
        return "explicit", [m.strip() for m in strong[:3]]

    weak = VISA_POSITIVE_WEAK.findall(text)
    if weak:
        return "possible", [m.strip() for m in weak[:3]]

    return "unknown", []


def make_job_id(job: Job) -> str:
    """SHA256 of company+title+location — stable across runs."""
    raw = f"{job.company.lower().strip()}|{job.title.lower().strip()}|{job.location.lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def apply_filters(jobs: List[Job]) -> List[Job]:
    """Classify visa status, assign job_id, and drop clear negatives."""
    results = []
    for job in jobs:
        combined_text = f"{job.title} {job.description} {job.location}"
        status, signals = classify_visa(combined_text)
        job.visa_status = status
        job.visa_signals = signals
        job.job_id = make_job_id(job)

        # Drop definitive negatives
        if status == "negative":
            continue
        results.append(job)
    return results
