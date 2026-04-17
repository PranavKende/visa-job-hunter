from __future__ import annotations
import os
from typing import List
from datetime import datetime
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.models import Job
from src.sources.base import BaseSource


ADZUNA_COUNTRIES = {"gb", "de", "nl", "ie", "ca", "au", "sg", "us", "at", "be", "br", "in", "nz", "pl", "ru", "za"}


class AdzunaSource(BaseSource):
    name = "adzuna"
    BASE_URL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"

    def __init__(self, config: dict):
        super().__init__(config)
        self.app_id = os.getenv("ADZUNA_APP_ID", "")
        self.app_key = os.getenv("ADZUNA_APP_KEY", "")
        self.results_per_page = config.get("results_per_page", 50)
        self.max_pages = config.get("max_pages", 3)

    async def fetch(self, keywords: List[str], locations: List[dict]) -> List[Job]:
        if not self.app_id or not self.app_key:
            logger.warning("Adzuna: missing ADZUNA_APP_ID or ADZUNA_APP_KEY — skipping")
            return []

        jobs: List[Job] = []
        supported = [loc for loc in locations if loc.get("adzuna_code") in ADZUNA_COUNTRIES]

        async with self._make_client() as client:
            for loc in supported:
                country = loc["adzuna_code"]
                for keyword in keywords:
                    fetched = await self._fetch_keyword(client, country, keyword, loc)
                    jobs.extend(fetched)
                    await self._sleep()

        logger.info(f"Adzuna: fetched {len(jobs)} jobs")
        return jobs

    async def _fetch_keyword(self, client: httpx.AsyncClient, country: str, keyword: str, loc: dict) -> List[Job]:
        jobs = []
        for page in range(1, self.max_pages + 1):
            url = self.BASE_URL.format(country=country, page=page)
            params = {
                "app_id": self.app_id,
                "app_key": self.app_key,
                "what": keyword,
                "results_per_page": self.results_per_page,
                "content-type": "application/json",
                "sort_by": "date",
            }
            try:
                resp = await self._get_with_retry(client, url, params)
                data = resp.json()
                results = data.get("results", [])
                if not results:
                    break
                for item in results:
                    job = self._parse(item, loc)
                    if job:
                        jobs.append(job)
                if len(results) < self.results_per_page:
                    break
            except Exception as exc:
                logger.error(f"Adzuna [{country}/{keyword}] page {page}: {exc}")
                break
        return jobs

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _get_with_retry(self, client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp

    def _parse(self, item: dict, loc: dict) -> Job | None:
        try:
            salary_min = salary_max = None
            salary_data = item.get("salary_min"), item.get("salary_max")
            if salary_data[0]:
                salary_min = float(salary_data[0])
            if salary_data[1]:
                salary_max = float(salary_data[1])

            posted_at = None
            created = item.get("created")
            if created:
                try:
                    posted_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except Exception:
                    pass

            return Job(
                title=item.get("title", ""),
                company=item.get("company", {}).get("display_name", "Unknown"),
                location=item.get("location", {}).get("display_name", loc.get("name", "")),
                country_code=loc.get("country_code", ""),
                description=item.get("description", ""),
                salary_min=salary_min,
                salary_max=salary_max,
                salary_currency="GBP" if loc["adzuna_code"] == "gb" else
                               "EUR" if loc["adzuna_code"] in ("de", "nl", "ie", "at", "be") else
                               "CAD" if loc["adzuna_code"] == "ca" else
                               "AUD" if loc["adzuna_code"] == "au" else
                               "SGD" if loc["adzuna_code"] == "sg" else "USD",
                apply_url=item.get("redirect_url", ""),
                source=self.name,
                posted_at=posted_at,
            )
        except Exception as exc:
            logger.debug(f"Adzuna parse error: {exc}")
            return None
