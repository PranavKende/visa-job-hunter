# Visa Sponsorship Job Hunter

Automated daily job search for Senior RPA / Intelligent Automation / Agentic AI roles with visa sponsorship across Europe, Canada, Australia, Singapore, and the Middle East.

Runs every morning at 7:00 AM IST via GitHub Actions and sends a ranked digest to your WhatsApp (CallMeBot) with Telegram as fallback.

---

## Quick Start

```bash
git clone <your-repo>
cd job-hunter
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env                              # fill in your keys
python -m src.main --dry-run                      # test without notifying
python -m src.main                                # live run
```

---

## API Keys Setup

### 1. CallMeBot (WhatsApp — primary notifier)

1. Add **+34 644 51 95 23** to your WhatsApp contacts (name it "CallMeBot").
2. Send this exact message to that number on WhatsApp:
   ```
   I allow callmebot to send me messages
   ```
3. You'll receive your API key in reply within a minute.
4. Set in `.env`:
   ```
   CALLMEBOT_PHONE=917276385283
   CALLMEBOT_API_KEY=<key_from_reply>
   ```

### 2. Adzuna (job search API — primary source)

1. Register at **https://developer.adzuna.com/signup**
2. Create an app — free tier gives 250 calls/day (enough for our usage).
3. Set in `.env`:
   ```
   ADZUNA_APP_ID=<your_app_id>
   ADZUNA_APP_KEY=<your_app_key>
   ```

### 3. Jooble (secondary source)

1. Request a free key at **https://jooble.org/api/about** (fill the contact form).
2. Set in `.env`:
   ```
   JOOBLE_KEY=<your_key>
   ```

### 4. Telegram Bot (fallback notifier — optional but recommended)

1. Message **@BotFather** on Telegram → `/newbot` → follow prompts.
2. Copy the bot token.
3. Start a chat with your new bot, then get your chat ID:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
4. Set in `.env`:
   ```
   TELEGRAM_BOT_TOKEN=<token>
   TELEGRAM_CHAT_ID=<your_chat_id>
   ```

---

## GitHub Actions Setup

Push this repo to GitHub, then add secrets at:
**Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `ADZUNA_APP_ID` | Your Adzuna app ID |
| `ADZUNA_APP_KEY` | Your Adzuna app key |
| `JOOBLE_KEY` | Your Jooble API key |
| `CALLMEBOT_PHONE` | `917276385283` |
| `CALLMEBOT_API_KEY` | Your CallMeBot key |
| `TELEGRAM_BOT_TOKEN` | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |

The workflow runs daily at **01:30 UTC (7:00 AM IST)** and can also be triggered manually from the Actions tab.

---

## Windows Task Scheduler (local alternative)

1. Open **Task Scheduler** → Create Basic Task
2. Trigger: Daily, 7:00 AM
3. Action: Start a Program → select `run.bat`
4. Check "Run whether user is logged on or not"

---

## Project Structure

```
job-hunter/
├── config.yaml              # keywords, geographies, scoring weights
├── src/
│   ├── models.py            # Pydantic Job model
│   ├── filters.py           # Visa-sponsorship regex classifier + dedup IDs
│   ├── scorer.py            # Weighted 0-100 scoring
│   ├── storage.py           # SQLite dedup + daily JSON audit
│   ├── notifier.py          # CallMeBot WhatsApp + Telegram fallback
│   ├── main.py              # Async orchestrator
│   └── sources/
│       ├── adzuna.py        # Adzuna API (GB, DE, NL, IE, CA, AU, SG)
│       ├── remotive.py      # Remotive API (remote roles)
│       ├── jooble.py        # Jooble API (global)
│       ├── arbeitnow.py     # Arbeitnow (Germany, visa-flagged)
│       ├── remoteok.py      # RemoteOK (remote tech roles)
│       └── relocateme.py    # Relocate.me scraper (relocation-focused)
├── data/
│   ├── jobs.db              # SQLite — seen job IDs (dedup store)
│   └── jobs_YYYY-MM-DD.json # Daily audit dumps
├── logs/                    # Rotating daily logs
├── .env                     # Your secrets (never commit this)
├── .env.example             # Template
├── requirements.txt
├── run.bat                  # Windows Task Scheduler launcher
└── .github/workflows/
    └── daily.yml            # GitHub Actions cron job
```

---

## Scoring Logic

| Signal | Points |
|---|---|
| Senior / Lead / Architect in title | +30 |
| UiPath / RPA / Intelligent Automation match | +20 |
| LangGraph / Agentic AI / LLM match | +15 |
| Target country match | +15 |
| 9+ years experience alignment | +10 |
| Explicit visa sponsorship | +10 |
| Possible visa signals | +5 |
| Junior / entry-level in title | -20 |
| Salary below $60K USD equivalent | -30 |

Only jobs scoring ≥ 40 are included in the WhatsApp digest.

---

## Visa Classification

| Status | Meaning |
|---|---|
| ✅ explicit | Job description contains strong visa/relocation signals |
| 🔶 possible | Weaker signals like "open to relocation", "international candidates" |
| ❓ unknown | No visa information found — included but unverified |
| ❌ negative | "No sponsorship", "citizens only" etc. — **filtered out** |

---

## Sources

| Source | Coverage | Auth required |
|---|---|---|
| Adzuna | GB, DE, NL, IE, CA, AU, SG | Free API key |
| Remotive | Remote globally | None |
| Jooble | Global | Free API key |
| Arbeitnow | Germany (visa-tagged) | None |
| RemoteOK | Remote tech globally | None |
| Relocate.me | Relocation-friendly roles | None (scrape) |
