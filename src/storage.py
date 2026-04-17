from __future__ import annotations
import sqlite3
import json
from datetime import datetime, date
from pathlib import Path
from typing import List
from loguru import logger
from src.models import Job

DB_PATH = Path(__file__).parent.parent / "data" / "jobs.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_jobs (
                job_id TEXT PRIMARY KEY,
                title TEXT,
                company TEXT,
                location TEXT,
                country_code TEXT,
                score INTEGER,
                visa_status TEXT,
                source TEXT,
                apply_url TEXT,
                salary_min REAL,
                salary_max REAL,
                salary_currency TEXT,
                first_seen DATE,
                raw_json TEXT
            )
        """)
        conn.commit()
    logger.debug("Storage: DB initialized")


def filter_new_jobs(jobs: List[Job]) -> List[Job]:
    """Return only jobs not yet in the DB."""
    if not jobs:
        return []
    init_db()
    existing_ids = set()
    with _connect() as conn:
        rows = conn.execute("SELECT job_id FROM seen_jobs").fetchall()
        existing_ids = {r["job_id"] for r in rows}

    new_jobs = [j for j in jobs if j.job_id not in existing_ids]
    logger.info(f"Storage: {len(jobs)} total, {len(new_jobs)} new (dedup removed {len(jobs)-len(new_jobs)})")
    return new_jobs


def save_jobs(jobs: List[Job]):
    if not jobs:
        return
    init_db()
    today = date.today().isoformat()
    with _connect() as conn:
        for job in jobs:
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO seen_jobs
                       (job_id, title, company, location, country_code, score, visa_status,
                        source, apply_url, salary_min, salary_max, salary_currency, first_seen, raw_json)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job.job_id, job.title, job.company, job.location,
                        job.country_code, job.score, job.visa_status,
                        job.source, job.apply_url,
                        job.salary_min, job.salary_max, job.salary_currency,
                        today, job.model_dump_json(),
                    ),
                )
            except Exception as exc:
                logger.error(f"Storage save error [{job.job_id}]: {exc}")
        conn.commit()
    logger.info(f"Storage: saved {len(jobs)} new jobs to DB")


def save_daily_json(jobs: List[Job], run_date: date | None = None):
    """Write full result set to data/jobs_YYYY-MM-DD.json for audit."""
    run_date = run_date or date.today()
    out_path = Path(__file__).parent.parent / "data" / f"jobs_{run_date.isoformat()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = [json.loads(j.model_dump_json()) for j in jobs]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"Storage: wrote {len(jobs)} jobs to {out_path}")
