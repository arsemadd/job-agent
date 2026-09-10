# Job Matcher

Personal job-matching agent for remote Product Management and QA roles. Collects public board postings, applies deterministic eligibility filters, scores survivors against a structured candidate profile (Gemini by default, Anthropic optional), and posts only threshold-clearing matches to Discord.

```
Collectors → dedupe → hard filters → AI match scoring → storage → Discord
```

The model returns a 0–100 score. SEND / DIGEST / REJECT is derived from that score against `config/preferences.json` thresholds — the model does not choose the routing decision.

## Features

- Sources: RemoteOK, Remotive, We Work Remotely, Himalayas, Mind the Product, Arbeitnow, Jobicy, Working Nomads, Remote First Jobs, NoDesk, Jobspresso, 4 Day Week, Greenhouse, Lever, Ashby (+ manual Wellfound / SaaS Jobs / Startup Jobs; discovery links for many more)
- Hard filters (role, location, experience, job type, company quality) before any AI call
- Swappable scorers: Gemini (default, free tier) or Anthropic Claude
- Discord: immediate alerts for strong matches (85+), digest for mid-band matches (65–84)
- FastAPI dashboard over `data/jobs.json`, plus LinkedIn / board discovery links
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
| `DISCORD_WEBHOOK_URL` | for notifications | channel webhook |
| `DISCORD_FORUM` | no | set `1` only if the webhook targets a forum channel |
| `DISCORD_THREAD_ID` | no | post into an existing forum thread |
| `DISCORD_THREAD_NAME` | no | forum post name when forum mode is on |
| `DISCORD_NOTIFY_EMPTY_RUNS` | no | `1` (default) posts a short run heartbeat |

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

Hourly **every hour UTC** (`cron: 0 * * * *`). GitHub Actions cron can delay or skip runs on public repos under load — if a slot is missed, the next hour usually picks up. Manual runs: Actions tab → `workflow_dispatch`.

Quiet runs still post a short Discord heartbeat when `DISCORD_NOTIFY_EMPTY_RUNS=1` (default), so you can tell the agent ran even when nothing scored ≥65.

## Sources

### Live collectors (public API / RSS)

| Source | Method | Notes |
|---|---|---|
| RemoteOK | Public API | |
| Remotive | Public API | Category queries |
| We Work Remotely | RSS | Uses `<region>` when present |
| Himalayas | Public API | Uses `locationRestrictions` when present |
| Mind the Product | Public JSON list | Product-focused board |
| Arbeitnow | Public API | Tag-hinted PM/QA subset |
| Jobicy | Public API | Product / QA / business remote queries |
| Working Nomads | Public JSON | `api/exposed_jobs` + local PM/QA filter |
| Remote First Jobs | Category RSS | `product`, `qa`, … |
| NoDesk | RSS | Product/QA title filter |
| Jobspresso | RSS | Job listing feed + PM/QA filter |
| 4 Day Week | Public API | Remote + product/QA queries |
| Greenhouse | Per-company board API | Tokens in `sources.greenhouse_boards` |
| Lever | Per-company API | Slugs in `sources.lever_companies` |
| Ashby | Per-company API | Slugs in `sources.ashby_companies` |

### Manual import (no scraping)

| Source | File | Notes |
|---|---|---|
| Wellfound | `data/wellfound_manual.json` | See example schema in collector docs |
| The SaaS Jobs | `data/thesaasjobs_manual.json` | Copy from `*.example.json` |
| Startup Jobs | `data/startupjobs_manual.json` | Cloudflare-gated site — manual only |

### Discovery only (dashboard links, never scraped)

LinkedIn, JustRemote, Dynamite Jobs, DailyRemote, Hiring Cafe, Jobgether, WeLoveProduct, Product Manager Job Board, Uxcel, Workello, TestDevJobs, Built In, Work at a Startup (YC), Underdog.io, Otta / Welcome to the Jungle, Remote100K, Arc, FlexJobs, PowerToFly, Virtual Vocations — all listed under Discovery in the dashboard (`/api/discovery`).

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
- `sources.greenhouse_boards` / `sources.lever_companies` / `sources.ashby_companies`

Keep `config/candidate_profile.json` in sync with the resume and portfolio so match rationale stays accurate.

## License

Private personal project — not published as an open-source package.
