# Job Matcher

Personal job-matching agent for remote Product Management and QA roles. Collects public board postings, applies deterministic eligibility filters, scores survivors against a structured candidate profile (Gemini by default, Anthropic optional), and posts only threshold-clearing matches to Discord.

```
Collectors → dedupe → hard filters → AI match scoring → storage → Discord
```

The model returns a 0–100 score. SEND / DIGEST / REJECT is derived from that score against `config/preferences.json` thresholds — the model does not choose the routing decision.

## Features

- Sources: RemoteOK, Remotive, We Work Remotely, Himalayas, Greenhouse, Lever
- Hard filters (role, location, experience, job type, company quality) before any AI call
- Swappable scorers: Gemini (default, free tier) or Anthropic Claude
- Discord: immediate alerts for strong matches (85+), digest for mid-band matches (65–84)
- FastAPI dashboard over `data/jobs.json`
- GitHub Actions hourly schedule; job store committed back to the repo

## Stack

| Layer | Choice |
|---|---|
| Pipeline | Python 3.12 |
| AI | Gemini (`google-genai`) or Anthropic |
| API / dashboard | FastAPI + vanilla HTML (Tailwind CDN) |
| Storage | `data/jobs.json` |
| CI | GitHub Actions |

## Configuration

| File | Purpose |
|---|---|
| `config/candidate_profile.json` | Resume + portfolio evidence the scorer reads |
| `config/preferences.json` | Roles, location tiers, experience rules, score thresholds, sources |
| `.env` | Local secrets (see `.env.example`) |

### Environment variables

| Variable | Required | Notes |
|---|---|---|
| `AI_PROVIDER` | no | `gemini` (default) or `anthropic` |
| `GEMINI_API_KEY` | if using Gemini | [Google AI Studio](https://aistudio.google.com/apikey) |
| `GEMINI_MODEL` | no | defaults to `gemini-3.5-flash-lite` |
| `ANTHROPIC_API_KEY` | if using Claude | |
| `ANTHROPIC_MODEL` | no | override default Claude model ID |
| `DISCORD_WEBHOOK_URL` | for notifications | channel webhook (forum channels supported) |
| `DISCORD_THREAD_ID` | no | post into an existing forum thread |
| `DISCORD_THREAD_NAME` | no | forum post name when `DISCORD_THREAD_ID` is unset |

GitHub Actions uses the same keys via repository **Secrets** / **Variables**.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # set GEMINI_API_KEY and DISCORD_WEBHOOK_URL

python -m backend.pipeline         # collect → filter → score → Discord
python -m backend.pipeline --dry-run

uvicorn backend.app:app --reload   # http://127.0.0.1:8000
pytest
```

## Scheduling

Hourly from **09:00 through 23:00 Africa/Nairobi** (`cron: 0 6-20 * * *` UTC). GitHub Actions cron is UTC-only; Nairobi is UTC+3 year-round, so this lines up with wall-clock hours. Each run commits an updated `data/jobs.json`. Trigger ad-hoc runs with `workflow_dispatch` on the Actions tab.

## Sources

| Source | Method | Notes |
|---|---|---|
| RemoteOK | Public API | |
| Remotive | Public API | Category queries |
| We Work Remotely | RSS | Uses `<region>` when present |
| Himalayas | Public API | Uses `locationRestrictions` when present |
| Greenhouse | Per-company board API | Tokens in `sources.greenhouse_boards` |
| Lever | Per-company API | Slugs in `sources.lever_companies` |
| Wellfound | Manual import | `data/wellfound_manual.json` if present (no scraping) |
| LinkedIn | Discovery links only | Search URLs, never scraped |

## Project layout

```
backend/
  collectors/      job sources → backend.models.Job
  filters/         role, location, experience, job_type, company_quality
  matching/        candidate profile + Gemini / Anthropic scorers
  notifications/   Discord webhook formatting
  storage/         data/jobs.json persistence + dedup
  pipeline.py      one full run
  app.py           FastAPI dashboard + /api/jobs, /api/stats
frontend/dashboard/index.html
config/            candidate_profile.json, preferences.json
data/jobs.json     job store (updated by scheduled runs)
tests/             pytest suite (mocked HTTP / AI — no live network)
.github/workflows/job-agent.yml
```

## Tuning

Edit `config/preferences.json`:

- `roles.include` / `roles.exclude_keywords`
- `experience.hard_reject_years`, seniority title rules
- `location` tier keyword lists
- `scoring.min_score_to_send_immediate` (default 85) / `min_score_to_send_digest` (default 65)
- `sources.greenhouse_boards` / `sources.lever_companies`

Keep `config/candidate_profile.json` in sync with the resume and portfolio so match rationale stays accurate.

## License

Private personal project — not published as an open-source package.
