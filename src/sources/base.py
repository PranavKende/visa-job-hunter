from __future__ import annotations
import asyncio
from abc import ABC, abstractmethod
from typing import List
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger
from src.models import Job


class BaseSource(ABC):
    name: str = "base"
    timeout: int = 30

    def __init__(self, config: dict):
        self.config = config
        self.rate_limit_delay = config.get("rate_limit_delay", 1.0)

    @abstractmethod
    async def fetch(self, keywords: List[str], locations: List[dict]) -> List[Job]:
        """Fetch jobs for given keywords and locations."""

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": "JobHunter/1.0 (personal automation; pranav.kende007@gmail.com)"},
            follow_redirects=True,
        )

    @staticmethod
    def _retry_decorator():
        return retry(
            retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )

    async def _sleep(self):
        await asyncio.sleep(self.rate_limit_delay)
