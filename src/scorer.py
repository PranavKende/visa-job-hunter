from __future__ import annotations
import re
from typing import List
from src.models import Job


SENIOR_PATTERN = re.compile(r"\b(senior|lead|principal|staff|architect|head\s+of)\b", re.IGNORECASE)
JUNIOR_PATTERN = re.compile(r"\b(junior|jr\.?|entry.?level|graduate|intern)\b", re.IGNORECASE)
UIPATH_RPA_PATTERN = re.compile(r"\b(uipath|blue\s+prism|rpa|robotic\s+process|intelligent\s+automation)\b", re.IGNORECASE)
AGENTIC_AI_PATTERN = re.compile(r"\b(langgraph|langchain|agentic|multi.agent|llm|genai|generative\s+ai|ai\s+agent)\b", re.IGNORECASE)

TARGET_COUNTRIES = {"gb", "de", "nl", "ie", "se", "dk", "no", "ca", "au", "nz", "sg", "my", "ae", "qa"}

# Approximate USD equivalents for common currencies (annual salary)
CURRENCY_TO_USD = {
    "GBP": 1.27, "EUR": 1.09, "CAD": 0.74, "AUD": 0.65,
    "SGD": 0.74, "AED": 0.27, "QAR": 0.27, "MYR": 0.23,
    "SEK": 0.096, "DKK": 0.146, "NOK": 0.095, "NZD": 0.60,
    "USD": 1.0,
}

SALARY_FLOOR_USD = 60_000


def score_job(job: Job, weights: dict | None = None) -> Job:
    breakdown: dict[str, int] = {}
    title = job.title or ""
    desc = job.description or ""
    combined = f"{title} {desc}"

    # +30 Senior/Lead/Architect in title — only if the TITLE itself is automation/AI relevant
    if SENIOR_PATTERN.search(title) and (UIPATH_RPA_PATTERN.search(title) or AGENTIC_AI_PATTERN.search(title)):
        breakdown["senior_lead_architect_title"] = 30
    elif SENIOR_PATTERN.search(title):
        # Generic senior role — smaller bonus
        breakdown["senior_title_generic"] = 10

    # -20 Junior in title
    if JUNIOR_PATTERN.search(title):
        breakdown["junior_title_penalty"] = -20

    # +20 UiPath / RPA match
    if UIPATH_RPA_PATTERN.search(combined):
        breakdown["uipath_rpa_match"] = 20

    # +15 Agentic AI / LangGraph
    if AGENTIC_AI_PATTERN.search(combined):
        breakdown["agentic_ai_langraph"] = 15

    # +15 Target country
    if job.country_code.lower() in TARGET_COUNTRIES:
        breakdown["target_country"] = 15

    # +10 Exp alignment (9+ years → "senior", "experienced", "9 years" etc.)
    if re.search(r"\b(9|10|11|12|\d{2})\+?\s*years?\b|\bsenior\b|\bexperienced\b", combined, re.IGNORECASE):
        breakdown["exp_alignment"] = 10

    # -30 Salary below floor
    salary_usd = _to_usd(job.salary_min or job.salary_max, job.salary_currency)
    if salary_usd is not None and salary_usd < SALARY_FLOOR_USD:
        breakdown["low_salary_penalty"] = -30

    # Visa bonus
    if job.visa_status == "explicit":
        breakdown["explicit_visa"] = 10
    elif job.visa_status == "possible":
        breakdown["possible_visa"] = 5

    total = sum(breakdown.values())
    job.score = max(0, min(100, total))
    job.score_breakdown = breakdown
    return job


def _to_usd(amount: float | None, currency: str) -> float | None:
    if amount is None:
        return None
    rate = CURRENCY_TO_USD.get(currency.upper(), 1.0)
    return amount * rate


def score_all(jobs: List[Job]) -> List[Job]:
    scored = [score_job(job) for job in jobs]
    return sorted(scored, key=lambda j: j.score, reverse=True)
