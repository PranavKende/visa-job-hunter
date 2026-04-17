from __future__ import annotations
from typing import List
from datetime import datetime
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.models import Job
from src.sources.base import BaseSource


class RemotiveSource(BaseSource):
    name = "remotive"
    BASE_URL = "https://remotive.com/api/remote-jobs"

    async def fetch(self, keywords: List[str], locations: List[dict]) -> List[Job]:
        jobs: List[Job] = []
        seen_ids: set[int] = set()

        async with self._make_client() as client:
            for keyword in keywords:
                try:
                    fetched = await self._fetch_keyword(client, keyword)
                    for job in fetched:
                        raw_id = id(job.apply_url)  # temp dedup within source
                        if job.apply_url not in seen_ids:
                            seen_ids.add(job.apply_url)
                            jobs.append(job)
                    await self._sleep()
                except Exception as exc:
                    logger.error(f"Remotive [{keyword}]: {exc}")

        logger.info(f"Remotive: fetched {len(jobs)} jobs")
        return jobs

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _fetch_keyword(self, client: httpx.AsyncClient, keyword: str) -> List[Job]:
        resp = await client.get(self.BASE_URL, params={"search": keyword, "limit": 100})
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for item in data.get("jobs", []):
            job = self._parse(item)
            if job:
                jobs.append(job)
        return jobs

    def _parse(self, item: dict) -> Job | None:
        try:
            posted_at = None
            pub_date = item.get("publication_date")
            if pub_date:
                try:
                    posted_at = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                except Exception:
                    pass

            return Job(
                title=item.get("title", ""),
                company=item.get("company_name", "Unknown"),
                location=item.get("candidate_required_location", "Remote"),
                country_code="",
                description=item.get("description", ""),
                apply_url=item.get("url", ""),
                source=self.name,
                posted_at=posted_at,
            )
        except Exception as exc:
            logger.debug(f"Remotive parse error: {exc}")
            return None
