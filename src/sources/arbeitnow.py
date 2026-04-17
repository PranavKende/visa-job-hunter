from __future__ import annotations
from typing import List
from datetime import datetime
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.models import Job
from src.sources.base import BaseSource


class ArbeitnowSource(BaseSource):
    """Arbeitnow — free job board focused on Germany, visa-friendly roles."""
    name = "arbeitnow"
    BASE_URL = "https://www.arbeitnow.com/api/job-board-api"

    async def fetch(self, keywords: List[str], locations: List[dict]) -> List[Job]:
        jobs: List[Job] = []
        seen_slugs: set[str] = set()

        async with self._make_client() as client:
            for page in range(1, 6):  # up to 5 pages, 100 jobs each
                try:
                    items = await self._fetch_page(client, page)
                    if not items:
                        break
                    for item in items:
                        slug = item.get("slug", "")
                        if slug and slug not in seen_slugs:
                            seen_slugs.add(slug)
                            job = self._parse(item)
                            if job:
                                jobs.append(job)
                    await self._sleep()
                except Exception as exc:
                    logger.error(f"Arbeitnow page {page}: {exc}")
                    break

        # Filter by keywords client-side (Arbeitnow has no search param)
        kw_lower = [k.lower() for k in keywords]
        filtered = [
            j for j in jobs
            if any(k in j.title.lower() or k in j.description.lower() for k in kw_lower)
        ]
        logger.info(f"Arbeitnow: fetched {len(jobs)} total, {len(filtered)} keyword-matched")
        return filtered

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _fetch_page(self, client: httpx.AsyncClient, page: int) -> list:
        resp = await client.get(self.BASE_URL, params={"page": page})
        resp.raise_for_status()
        return resp.json().get("data", [])

    def _parse(self, item: dict) -> Job | None:
        try:
            posted_at = None
            created = item.get("created_at")
            if created:
                try:
                    posted_at = datetime.fromtimestamp(created)
                except Exception:
                    pass

            tags: list = item.get("tags", [])
            description = item.get("description", "")
            # Arbeitnow marks visa-sponsored roles explicitly
            if item.get("visa_sponsorship"):
                description = "[VISA SPONSORSHIP AVAILABLE] " + description

            return Job(
                title=item.get("title", ""),
                company=item.get("company_name", "Unknown"),
                location=item.get("location", "Germany"),
                country_code="de",
                description=description,
                apply_url=item.get("url", f"https://www.arbeitnow.com/jobs/{item.get('slug','')}"),
                source=self.name,
                posted_at=posted_at,
            )
        except Exception as exc:
            logger.debug(f"Arbeitnow parse error: {exc}")
            return None
