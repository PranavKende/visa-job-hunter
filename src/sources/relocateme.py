from __future__ import annotations
from typing import List
from datetime import datetime
import xml.etree.ElementTree as ET
import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.models import Job
from src.sources.base import BaseSource

# Relocate.me is a JS SPA with no public API or RSS.
# We use WeWorkRemotely (similar audience: remote + relocation) which provides
# a public RSS feed at https://weworkremotely.com/remote-jobs.rss
# Kept as "relocateme" source name to avoid config churn.


class RelocateMeSource(BaseSource):
    name = "relocateme"  # kept as-is; actually fetches WeWorkRemotely
    RSS_URL = "https://weworkremotely.com/remote-jobs.rss"

    async def fetch(self, keywords: List[str], locations: List[dict]) -> List[Job]:
        jobs: List[Job] = []
        kw_lower = [k.lower() for k in keywords]

        async with self._make_client() as client:
            try:
                all_jobs = await self._fetch_rss(client)
                for job in all_jobs:
                    title_l = job.title.lower()
                    desc_l = job.description.lower()
                    if any(k in title_l or k in desc_l for k in kw_lower):
                        jobs.append(job)
                await self._sleep()
            except Exception as exc:
                logger.error(f"WeWorkRemotely (relocateme slot): {exc}")

        logger.info(f"WeWorkRemotely: fetched {len(jobs)} keyword-matched jobs")
        return jobs

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def _fetch_rss(self, client: httpx.AsyncClient) -> List[Job]:
        resp = await client.get(self.RSS_URL, headers={"Accept": "application/rss+xml,application/xml,text/xml"})
        resp.raise_for_status()
        return self._parse_rss(resp.text)

    def _parse_rss(self, xml_text: str) -> List[Job]:
        jobs = []
        try:
            root = ET.fromstring(xml_text)
            channel = root.find("channel")
            if channel is None:
                return jobs
            for item in channel.findall("item"):
                try:
                    title = item.findtext("title", "").strip()
                    link = item.findtext("link", "").strip()
                    description = item.findtext("description", "").strip()
                    pub_date_str = item.findtext("pubDate", "")

                    posted_at = None
                    if pub_date_str:
                        try:
                            from email.utils import parsedate_to_datetime
                            posted_at = parsedate_to_datetime(pub_date_str)
                        except Exception:
                            pass

                    # WWR title format: "Company: Job Title"
                    company = "Unknown"
                    if ": " in title:
                        parts = title.split(": ", 1)
                        company, title = parts[0].strip(), parts[1].strip()

                    jobs.append(Job(
                        title=title,
                        company=company,
                        location="Remote / Worldwide",
                        country_code="",
                        description=description,
                        apply_url=link,
                        source=self.name,
                        posted_at=posted_at,
                    ))
                except Exception as exc:
                    logger.debug(f"WeWorkRemotely item parse error: {exc}")
        except ET.ParseError as exc:
            logger.error(f"WeWorkRemotely RSS parse failed: {exc}")
        return jobs
