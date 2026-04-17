from __future__ import annotations
import re
import hashlib
from typing import List, Tuple
from src.models import Job


# ── Negative patterns (checked FIRST) ────────────────────────────────────────
# Must catch negations BEFORE the positive word appears in the same sentence
VISA_NEGATIVE = re.compile(
    r"no\s+visa\s+sponsor(?:ship)?|"
    r"sponsor(?:ship)?\s+available\s*:\s*not\s+available|"
    r"visa\s+sponsor(?:ship)?\s+(?:is\s+)?not\s+(?:available|offered|provided)|"
    r"sponsor(?:ship)?\s+(?:is\s+)?not\s+available|"
    r"not\s+(?:offer|provide|accept|support)\s+(?:visa\s+)?sponsor|"
    r"(?:is|are|am)\s+not\s+able\s+to\s+sponsor|"
    r"isn'?t\s+able\s+to\s+sponsor|"
    r"unable\s+to\s+(?:offer\s+)?(?:visa\s+)?sponsor|"
    r"must\s+(?:already\s+)?have\s+(?:valid\s+)?(?:the\s+)?(?:right\s+to\s+work|work\s+(?:authoriz|permit))|"
    r"right\s+to\s+work\s+in\s+the\s+uk\s+(?:is\s+)?required|"
    r"citizens?\s+(?:and\s+permanent\s+residents?\s+)?only|"
    r"(?:permanent\s+)?residents?\s+only|"
    r"\bpr\s+(?:holder|required|only)\b|"
    r"do\s+not\s+(?:offer|provide)\s+sponsorship|"
    r"no\s+(?:relocation|sponsorship)\s+(?:assistance|support|offered|available)|"
    r"local\s+candidates?\s+only|"
    r"eu\s+(?:passport|citizen)\s+(?:required|only)|"
    r"no\s+need\s+for\s+(?:current\s+or\s+future\s+)?visa\s+sponsor|"
    r"without\s+(?:the\s+)?need\s+for\s+(?:visa\s+)?sponsor|"
    r"not\s+available\s+at\s+this\s+time",
    re.IGNORECASE,
)

# ── Strong positive patterns ──────────────────────────────────────────────────
VISA_POSITIVE_STRONG = re.compile(
    r"\bwill\s+sponsor\s+(?:your\s+)?visa\b|"
    r"\bvisa\s+sponsorship\s+(?:is\s+)?(?:provided|available|offered|included|supported)\b|"
    r"\bsponsorship\s+(?:is\s+)?available\b(?!\s*:\s*not)|"  # "Sponsorship Available" but NOT "Sponsorship Available: Not"
    r"\bwe\s+(?:do\s+|will\s+)?sponsor\b|"
    r"\bsponsoring\s+(?:your\s+)?visa\b|"
    r"\brelocation\s+(?:assistance|support|package)\s+(?:provided|available|offered|included)\b|"
    r"\bblue\s+card\b|"
    r"\bskilled\s+worker\s+visa\b|"
    r"\blmia\s+(?:approved|eligible|supported)\b|"
    r"\bict\s+visa\b|"
    r"\b482\s+visa\b|"
    r"\bemployment\s+pass\s+(?:provided|eligible|supported)\b|"
    r"\bwork\s+permit\s+(?:provided|sponsored|supported)\b",
    re.IGNORECASE,
)

# ── Weak positive patterns ────────────────────────────────────────────────────
VISA_POSITIVE_WEAK = re.compile(
    r"\bopen\s+to\s+relocation\b|"
    r"\brelocation\s+(?:package|support)\b|"
    r"\binternational\s+(?:candidates|applicants)\s+welcome\b|"
    r"\bglobal\s+mobility\b|"
    r"\bwork\s+authorization\s+support\b",
    re.IGNORECASE,
)

# ── RPA / automation relevance gate ──────────────────────────────────────────
# Job must mention at least one of these to be considered relevant
RELEVANCE_PATTERN = re.compile(
    r"\b(rpa|uipath|blue\s+prism|robotic\s+process|intelligent\s+automation|"
    r"automation\s+(?:engineer|architect|lead|developer|specialist|consultant)|"
    r"langgraph|langchain|agentic\s+ai|multi.agent|celonis|process\s+mining|"
    r"workflow\s+automation|hyperautomation|power\s+automate)\b",
    re.IGNORECASE,
)


def _check_negation_context(text: str, match_start: int) -> bool:
    """Return True if a negation word appears within 60 chars before the match."""
    window = text[max(0, match_start - 60): match_start]
    return bool(re.search(r"\b(no|not|never|without|unable|isn'?t|aren'?t|cannot|can'?t)\b", window, re.IGNORECASE))


def classify_visa(text: str) -> Tuple[str, List[str]]:
    """Return (status, matched_signals). Status: explicit | possible | negative | unknown."""

    # Negative check first — catches explicit rejections
    neg_match = VISA_NEGATIVE.search(text)
    if neg_match:
        return "negative", [neg_match.group().strip()]

    # Strong positive — but verify no negation in the 60 chars before it
    for m in VISA_POSITIVE_STRONG.finditer(text):
        if not _check_negation_context(text, m.start()):
            signals = [m.group().strip() for m in VISA_POSITIVE_STRONG.finditer(text)][:3]
            return "explicit", signals

    # Weak positive
    for m in VISA_POSITIVE_WEAK.finditer(text):
        if not _check_negation_context(text, m.start()):
            signals = [m.group().strip() for m in VISA_POSITIVE_WEAK.finditer(text)][:3]
            return "possible", signals

    return "unknown", []


def is_relevant(job: Job) -> bool:
    """Job must mention RPA/automation keywords to pass relevance gate."""
    combined = f"{job.title} {job.description}"
    return bool(RELEVANCE_PATTERN.search(combined))


def make_job_id(job: Job) -> str:
    """SHA256 of company+title+location — stable across runs."""
    raw = f"{job.company.lower().strip()}|{job.title.lower().strip()}|{job.location.lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()


def apply_filters(jobs: List[Job]) -> List[Job]:
    """Classify visa status, assign job_id, drop negatives and irrelevant jobs."""
    results = []
    dropped_negative = 0
    dropped_irrelevant = 0

    for job in jobs:
        combined_text = f"{job.title} {job.description} {job.location}"
        status, signals = classify_visa(combined_text)
        job.visa_status = status
        job.visa_signals = signals
        job.job_id = make_job_id(job)

        if status == "negative":
            dropped_negative += 1
            continue

        if not is_relevant(job):
            dropped_irrelevant += 1
            continue

        results.append(job)

    from loguru import logger
    logger.info(f"Filters: dropped {dropped_negative} negative-visa, {dropped_irrelevant} irrelevant jobs")
    return results
