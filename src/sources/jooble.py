from __future__ import annotations
import os
from typing import List
from datetime import datetime
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.models import Job
from src.sources.base import BaseSource


class JoobleSource(BaseSource):
    name = "jooble"
    BASE_URL = "https://jooble.org/api/{key}"

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = os.getenv("JOOBLE_KEY", "")
        self.results_per_page = config.get("results_per_page", 20)
        self.max_pages = config.get("max_pages", 5)

    async def fetch(self, keywords: List[str], locations: List[dict]) -> List[Job]:
        if not self.api_key or self.api_key.startswith("your_") or self.api_key.startswith("http"):
            logger.warning("Jooble: missing or placeholder JOOBLE_KEY — skipping")
            return []

        jobs: List[Job] = []
        seen_urls: set[str] = set()

        async with self._make_client() as client:
            for loc in locations:
                for keyword in keywords:
                    try:
                        fetched = await self._fetch_page(client, keyword, loc, page=1)
                        for job in fetched:
                            if job.apply_url not in seen_urls:
                                seen_urls.add(job.apply_url)
                                jobs.append(job)
                        await self._sleep()
                    except Exception as exc:
                        logger.error(f"Jooble [{loc['name']}/{keyword}]: {exc}")

        logger.info(f"Jooble: fetched {len(jobs)} jobs")
        return jobs

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _fetch_page(self, client: httpx.AsyncClient, keyword: str, loc: dict, page: int) -> List[Job]:
        url = self.BASE_URL.format(key=self.api_key)
        payload = {
            "keywords": keyword,
            "location": loc["name"],
            "page": page,
            "resultonpage": self.results_per_page,
        }
        resp = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for item in data.get("jobs", []):
            job = self._parse(item, loc)
            if job:
                jobs.append(job)
        return jobs

    def _parse(self, item: dict, loc: dict) -> Job | None:
        try:
            posted_at = None
            updated = item.get("updated")
            if updated:
                try:
                    posted_at = datetime.fromisoformat(updated)
                except Exception:
                    pass

            salary_min = salary_max = None
            salary_str = item.get("salary", "")
            # Jooble returns salary as a string like "$50,000 - $80,000"
            # We store raw and let scorer handle it

            return Job(
                title=item.get("title", ""),
                company=item.get("company", "Unknown"),
                location=item.get("location", loc.get("name", "")),
                country_code=loc.get("country_code", ""),
                description=item.get("snippet", ""),
                apply_url=item.get("link", ""),
                source=self.name,
                posted_at=posted_at,
            )
        except Exception as exc:
            logger.debug(f"Jooble parse error: {exc}")
            return None
