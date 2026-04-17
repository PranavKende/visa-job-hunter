from __future__ import annotations
import os
from datetime import date
from urllib.parse import quote
from typing import List
import httpx
from loguru import logger
from src.models import Job


CALLMEBOT_URL = "https://api.callmebot.com/whatsapp.php"
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"

VISA_EMOJI = {"explicit": "✅", "possible": "🔶", "unknown": "❓", "negative": "❌"}


def _format_salary(job: Job) -> str:
    if job.salary_min and job.salary_max:
        return f"{job.salary_currency} {job.salary_min/1000:.0f}K-{job.salary_max/1000:.0f}K"
    if job.salary_min:
        return f"{job.salary_currency} {job.salary_min/1000:.0f}K+"
    if job.salary_max:
        return f"up to {job.salary_currency} {job.salary_max/1000:.0f}K"
    return "Not listed"


def build_message(jobs: List[Job], total_found: int, failed_sources: List[str], run_date: date | None = None) -> List[str]:
    """Build WhatsApp-friendly message(s), split at 1000 chars."""
    run_date = run_date or date.today()
    top = jobs[:10]
    extra = total_found - len(top)

    header = (
        f"🎯 Daily Job Digest — {run_date.strftime('%d %b %Y')}\n"
        f"{total_found} new visa-sponsored roles\n\n"
    )
    if failed_sources:
        header += f"⚠️ Sources with issues: {', '.join(failed_sources)}\n\n"

    lines = []
    for i, job in enumerate(top, 1):
        visa_icon = VISA_EMOJI.get(job.visa_status, "❓")
        salary_str = _format_salary(job)
        line = (
            f"{i}. [Score:{job.score}] {job.title} — {job.company} ({job.location})\n"
            f"   Visa: {visa_icon} {job.visa_status} | Salary: {salary_str}\n"
            f"   {job.apply_url}\n"
        )
        lines.append(line)

    if extra > 0:
        lines.append(f"\n…and {extra} more roles found today.\n")

    # Split into chunks ≤ 1000 chars
    chunks: List[str] = []
    current = header
    for line in lines:
        if len(current) + len(line) > 1000:
            chunks.append(current.strip())
            current = line
        else:
            current += line
    if current.strip():
        chunks.append(current.strip())

    return chunks or [header.strip()]


async def send_whatsapp(message: str) -> bool:
    phone = os.getenv("CALLMEBOT_PHONE", "")
    api_key = os.getenv("CALLMEBOT_API_KEY", "")
    if not phone or not api_key:
        logger.warning("CallMeBot: missing CALLMEBOT_PHONE or CALLMEBOT_API_KEY")
        return False

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                CALLMEBOT_URL,
                params={"phone": phone, "text": message, "apikey": api_key},
            )
            if resp.status_code == 200:
                logger.info("CallMeBot: message sent successfully")
                return True
            logger.warning(f"CallMeBot: HTTP {resp.status_code} — {resp.text[:200]}")
            return False
        except Exception as exc:
            logger.error(f"CallMeBot error: {exc}")
            return False


async def send_telegram(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        logger.warning("Telegram: missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
        return False

    url = TELEGRAM_URL.format(token=token)
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"})
            if resp.status_code == 200:
                logger.info("Telegram: message sent successfully")
                return True
            logger.warning(f"Telegram: HTTP {resp.status_code} — {resp.text[:200]}")
            return False
        except Exception as exc:
            logger.error(f"Telegram error: {exc}")
            return False


async def notify(jobs: List[Job], total_found: int, failed_sources: List[str]):
    """Send digest via CallMeBot; fall back to Telegram on failure."""
    if not jobs and not failed_sources:
        logger.info("Notifier: nothing to send")
        return

    chunks = build_message(jobs, total_found, failed_sources)
    for chunk in chunks:
        success = await send_whatsapp(chunk)
        if not success:
            logger.info("Notifier: CallMeBot failed, trying Telegram fallback")
            await send_telegram(chunk)
