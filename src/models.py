from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Job(BaseModel):
    job_id: str = ""  # SHA256 set by storage layer
    title: str
    company: str
    location: str
    country_code: str = ""
    description: str = ""
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "USD"
    apply_url: str
    source: str
    posted_at: Optional[datetime] = None
    fetched_at: datetime = Field(default_factory=datetime.utcnow)

    # Set by filter layer
    visa_status: str = "unknown"  # explicit | possible | negative | unknown
    visa_signals: list[str] = Field(default_factory=list)

    # Set by scorer layer
    score: int = 0
    score_breakdown: dict[str, int] = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
