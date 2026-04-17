from __future__ import annotations
from typing import List
from datetime import datetime
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.models import Job
from src.sources.base import BaseSource


class RemoteOKSource(BaseSource):
    name = "remoteok"
    BASE_URL = "https://remoteok.com/api"

    async def fetch(self, keywords: List[str], locations: List[dict]) -> List[Job]:
        jobs: List[Job] = []
        kw_lower = [k.lower() for k in keywords]

        async with self._make_client() as client:
            try:
                all_jobs = await self._fetch_all(client)
                for item in all_jobs:
                    if not isinstance(item, dict) or "id" not in item:
                        continue
                    title = item.get("position", "").lower()
                    tags = " ".join(item.get("tags", [])).lower()
                    desc = item.get("description", "").lower()
                    if any(k in title or k in tags or k in desc for k in kw_lower):
                        job = self._parse(item)
                        if job:
                            jobs.append(job)
            except Exception as exc:
                logger.error(f"RemoteOK: {exc}")

        logger.info(f"RemoteOK: fetched {len(jobs)} keyword-matched jobs")
        return jobs

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _fetch_all(self, client: httpx.AsyncClient) -> list:
        # RemoteOK requires a non-browser UA to get JSON; they return first item as legal notice
        resp = await client.get(self.BASE_URL, headers={"User-Agent": "curl/7.68.0"})
        resp.raise_for_status()
        data = resp.json()
        return data[1:] if data else []  # skip legal notice at index 0

    def _parse(self, item: dict) -> Job | None:
        try:
            posted_at = None
            epoch = item.get("epoch")
            if epoch:
                try:
                    posted_at = datetime.utcfromtimestamp(int(epoch))
                except Exception:
                    pass

            salary_min = salary_max = None
            if item.get("salary_min"):
                salary_min = float(item["salary_min"])
            if item.get("salary_max"):
                salary_max = float(item["salary_max"])

            return Job(
                title=item.get("position", ""),
                company=item.get("company", "Unknown"),
                location=item.get("location", "Remote"),
                country_code="",
                description=item.get("description", ""),
                salary_min=salary_min,
                salary_max=salary_max,
                salary_currency="USD",
                apply_url=item.get("apply_url") or f"https://remoteok.com/remote-jobs/{item.get('id','')}",
                source=self.name,
                posted_at=posted_at,
            )
        except Exception as exc:
            logger.debug(f"RemoteOK parse error: {exc}")
            return None
