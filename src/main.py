from __future__ import annotations
import asyncio
import sys
from datetime import date
from pathlib import Path
from typing import List

import yaml
from dotenv import load_dotenv
from loguru import logger

from src.models import Job
from src.filters import apply_filters
from src.scorer import score_all
from src.storage import filter_new_jobs, save_jobs, save_daily_json
from src.notifier import notify
from src.llm_reranker import llm_rerank
from src.sources import (
    AdzunaSource,
    RemotiveSource,
    JoobleSource,
    ArbeitnowSource,
    RemoteOKSource,
    RelocateMeSource,
)

ROOT = Path(__file__).parent.parent


def load_config() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(cfg: dict):
    log_dir = ROOT / cfg.get("log_dir", "logs")
    log_dir.mkdir(exist_ok=True)
    logger.remove()
    logger.add(sys.stderr, level=cfg.get("level", "INFO"), colorize=True)
    logger.add(
        str(log_dir / "job_hunter_{time:YYYY-MM-DD}.log"),
        rotation=cfg.get("rotation", "1 day"),
        retention=cfg.get("retention", "30 days"),
        level="DEBUG",
        encoding="utf-8",
    )


def get_all_locations(cfg: dict) -> List[dict]:
    locations = []
    for region in cfg["geographies"].values():
        locations.extend(region)
    return locations


def build_source_instances(cfg: dict) -> list:
    sources_cfg = cfg.get("sources", {})
    enabled = []
    mapping = {
        "adzuna": AdzunaSource,
        "remotive": RemotiveSource,
        "jooble": JoobleSource,
        "arbeitnow": ArbeitnowSource,
        "remoteok": RemoteOKSource,
        "relocateme": RelocateMeSource,
    }
    for name, cls in mapping.items():
        src_cfg = sources_cfg.get(name, {})
        if src_cfg.get("enabled", True):
            enabled.append(cls(src_cfg))
    return enabled


async def fetch_source(source, keywords: List[str], locations: List[dict]) -> tuple[list, str | None]:
    """Fetch from one source; return (jobs, error_name_or_None)."""
    try:
        jobs = await source.fetch(keywords, locations)
        logger.info(f"Source {source.name}: {len(jobs)} jobs fetched")
        return jobs, None
    except Exception as exc:
        logger.error(f"Source {source.name} FAILED: {exc}")
        return [], source.name


async def run(dry_run: bool = False):
    load_dotenv(ROOT / ".env")           # job-hunter/.env
    load_dotenv(ROOT.parent / ".env")    # parent folder fallback
    cfg = load_config()
    setup_logging(cfg.get("logging", {}))

    logger.info("=" * 60)
    logger.info(f"Job Hunter starting — {date.today()}")

    keywords = cfg["keywords"]["primary"] + cfg["keywords"].get("secondary", [])
    locations = get_all_locations(cfg)
    sources = build_source_instances(cfg)

    logger.info(f"Sources enabled: {[s.name for s in sources]}")
    logger.info(f"Keywords: {len(keywords)}, Locations: {len(locations)}")

    # Fetch all sources in parallel
    tasks = [fetch_source(s, keywords, locations) for s in sources]
    results = await asyncio.gather(*tasks)

    all_jobs: List[Job] = []
    failed_sources: List[str] = []
    for jobs, err in results:
        all_jobs.extend(jobs)
        if err:
            failed_sources.append(err)

    if len(failed_sources) >= 2:
        logger.warning(f"⚠️ {len(failed_sources)} sources failed: {failed_sources}")

    # Zero-result detection
    for source in sources:
        source_jobs = [j for j in all_jobs if j.source == source.name]
        if not source_jobs and source.name not in failed_sources:
            logger.warning(f"Source {source.name}: returned ZERO jobs — possible silent failure")

    logger.info(f"Total raw jobs: {len(all_jobs)}")

    # Filter + classify visa
    filtered = apply_filters(all_jobs)
    logger.info(f"After visa filter (removed negatives): {len(filtered)}")

    # Score + sort
    scored = score_all(filtered)

    # Dedup against DB
    new_jobs = filter_new_jobs(scored)

    # Save daily JSON audit
    save_daily_json(scored, date.today())

    min_score = cfg.get("notification", {}).get("min_score_to_notify", 30)

    # Hard drop: only skip jobs with confirmed-negative visa status
    non_negative = [j for j in new_jobs if j.visa_status != "negative"]

    # Take top 30 by score and send to GPT for visa + relevance verification
    candidates = [j for j in non_negative if j.score >= min_score][:30]
    visa_confirmed = [j for j in new_jobs if j.visa_status in ("explicit", "possible")]

    logger.info(
        f"New jobs: {len(new_jobs)} | visa-confirmed (regex): {len(visa_confirmed)} | "
        f"candidates for LLM: {len(candidates)}"
    )

    # GPT-4o-mini verifies: is visa sponsorship realistic + is role RPA-relevant?
    notify_jobs = await llm_rerank(candidates)
    logger.info(
        f"New jobs: {len(new_jobs)} | visa-confirmed (regex): {len(visa_confirmed)} | "
        f"notifiable (score≥{min_score}): {len(notify_jobs)}"
    )

    if not dry_run:
        # Persist to DB
        save_jobs(new_jobs)
        await notify(notify_jobs, len(notify_jobs), failed_sources)
    else:
        logger.info("DRY RUN — skipping DB save and notification")
        if notify_jobs:
            logger.info("Top 5 jobs that would be sent:")
            for job in notify_jobs[:5]:
                logger.info(f"  [{job.score}] {job.title} @ {job.company} ({job.location}) | visa={job.visa_status}")

    logger.info("Job Hunter run complete")
    return notify_jobs


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Visa Sponsorship Job Hunter")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and score without saving/notifying")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
