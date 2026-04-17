from __future__ import annotations
import os
import json
import asyncio
from typing import List
from loguru import logger
from src.models import Job

SYSTEM_PROMPT = """You are a job filter assistant for a Senior RPA Engineer based in India looking to relocate abroad with visa sponsorship.

Candidate profile:
- 9+ years experience in RPA: UiPath (Studio, Orchestrator, Maestro, RE Framework), Blue Prism
- Skills: LangGraph, LangChain, Agentic AI, Multi-Agent LLM systems, Python, VB.NET, C#, SQL, Celonis
- Target roles: Senior RPA Engineer, RPA Team Lead, RPA Architect, Intelligent Automation Lead, AI Automation Engineer
- Hard requirement: employer must be open to sponsoring a work visa for someone relocating from India

For each job evaluate TWO things:

1. VISA: Is this employer LIKELY to sponsor a work visa for an Indian candidate?
   - "yes" = job explicitly mentions sponsorship/relocation, OR it's a senior role at a large/multinational company in a country that routinely sponsors (Germany Blue Card, UK Skilled Worker, Canada, Australia, Singapore, UAE) and the description does NOT say "must have right to work" or "no sponsorship"
   - "no" = description says no sponsorship, must be authorized, citizens/PR only, right to work required
   - "unclear" = small company, no mention either way, or ambiguous

2. RELEVANT: Is this role genuinely about RPA / Intelligent Automation / Agentic AI?
   - true = involves UiPath, Blue Prism, RPA platforms, automation development, LangGraph/LangChain agents
   - false = generic software engineer, data engineer, ML engineer without automation focus

Only pass jobs where visa="yes" AND relevant=true.

Respond ONLY with a JSON object: {"results": [{"visa": "yes|no|unclear", "relevant": true|false, "reason": "one sentence"}, ...]}
Same order as input."""


async def llm_rerank(jobs: List[Job]) -> List[Job]:
    """Re-rank visa-confirmed jobs using GPT-4o-mini. Returns only genuinely valid jobs."""
    if not jobs:
        return []

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("LLM reranker: no OPENAI_API_KEY — skipping")
        return jobs

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=api_key)
    except ImportError:
        logger.warning("LLM reranker: openai package not installed — skipping")
        return jobs

    # Build compact job descriptions for the prompt (keep costs low)
    job_inputs = []
    for i, job in enumerate(jobs):
        desc_snippet = job.description[:800] if job.description else ""
        job_inputs.append({
            "id": i,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "description": desc_snippet,
        })

    user_message = json.dumps(job_inputs, ensure_ascii=False)

    try:
        logger.info(f"LLM reranker: sending {len(jobs)} jobs to GPT-4o-mini")
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        raw = response.choices[0].message.content
        # GPT returns {"results": [...]} or just [...] — handle both
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            results = parsed.get("results", parsed.get("jobs", list(parsed.values())[0]))
        else:
            results = parsed

        passed = []
        for job, result in zip(jobs, results):
            visa_ok = result.get("visa") == "yes"
            relevant = result.get("relevant", False)
            reason = result.get("reason", "")
            logger.info(f"  [{job.title[:50]}] visa={result.get('visa')} relevant={relevant} — {reason}")
            if visa_ok and relevant:
                passed.append(job)

        logger.info(f"LLM reranker: {len(jobs)} in → {len(passed)} passed")
        return passed

    except Exception as exc:
        logger.error(f"LLM reranker failed: {exc} — returning unfiltered jobs")
        return jobs
