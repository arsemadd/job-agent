# Job Matcher

A personal job-matching agent — not a scraper that forwards every posting. It collects remote PM/QA
roles, runs deterministic eligibility filters (location, experience, role), scores the survivors
against your actual resume + portfolio using an AI model, and only sends the strongest matches to
Discord. The scoring backend is swappable: **Gemini** (Google's free API tier, $0 to run) or
**Anthropic Claude** (paid, but only a few dollars/month at this volume) — pick with `AI_PROVIDER`.

```
Collectors -> dedupe -> hard filters (role/location/experience/company) -> AI match scoring -> store -> Discord
```

Only jobs that pass the hard filters ever reach the AI, and the AI never decides SEND/DIGEST/REJECT on
its own — that's computed deterministically from its score against your thresholds in
`config/preferences.json`. See `config/candidate_profile.json` for the resume + portfolio evidence the
matcher uses, and the module docstrings in `backend/` for the reasoning behind each filter.

## 1. One-time setup

### Discord webhook
Server Settings -> Integrations -> Webhooks -> New Webhook -> pick a channel -> Copy Webhook URL.

### AI scoring key

Pick one (`AI_PROVIDER` controls which; defaults to `gemini`):

- **Gemini (free)** — create a key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey),
  no billing required to start. Check
  [ai.google.dev/gemini-api/docs/pricing](https://ai.google.dev/gemini-api/docs/pricing) for the current
  free-tier model list and rate limits — `backend/matching/scoring_gemini.py` defaults to
  `gemini-2.5-flash`; override with `GEMINI_MODEL` if that's no longer free-tier-eligible by the time
  you're reading this.
- **Anthropic Claude (paid)** — create one at
  [console.anthropic.com](https://console.anthropic.com) (Settings -> API Keys). No dedicated free tier,
  but new accounts get a small free credit, and this workload (a few dozen jobs scored per run, twice a
  day) runs only a few dollars a month even without it. Check
  [docs.claude.com/en/docs/about-claude/models](https://docs.claude.com/en/docs/about-claude/models) for
  the current model catalog and override with `ANTHROPIC_MODEL` if needed.

### Push this repo to GitHub
```bash
git init
git add .
git commit -m "Initial job matcher"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```

### Add repo secrets (Settings -> Secrets and variables -> Actions)
- `DISCORD_WEBHOOK_URL`
- `GEMINI_API_KEY` (if using the default free provider) or `ANTHROPIC_API_KEY` (if using Claude)
- optional Actions **variables** (not secrets): `AI_PROVIDER` (`gemini` or `anthropic`, defaults to
  `gemini`), `GEMINI_MODEL` / `ANTHROPIC_MODEL` to override the default model

That's it — `.github/workflows/job-agent.yml` runs the pipeline at 08:00 and 18:00 Africa/Nairobi time
every day and commits the updated `data/jobs.json` back to the repo. Trigger a run immediately from the
Actions tab (`workflow_dispatch`) instead of waiting for the schedule.

## 2. Running locally

```bash
pip install -r requirements-dev.txt
cp .env.example .env   # fill in GEMINI_API_KEY (or ANTHROPIC_API_KEY) and DISCORD_WEBHOOK_URL
export $(grep -v '^#' .env | xargs)   # or use python-dotenv / direnv

python -m backend.pipeline               # full run: collect, filter, score, notify
python -m backend.pipeline --dry-run     # collect + hard-filter only, no AI calls, no Discord
```

### Dashboard
```bash
uvicorn backend.app:app --reload
```
Open http://127.0.0.1:8000 — reads whatever is currently in `data/jobs.json` (the same file the GitHub
Action commits), so you can browse the latest scored jobs without re-running the pipeline. Click a row
for the full breakdown: why it matched, the gaps the AI flagged, and the apply link.

## 3. Tests

```bash
pytest
```
Covers dedup, all three hard filters (with an evaluation set of obvious-reject / obvious-pass /
ambiguous-5-6-year cases to catch false positives and negatives), the Discord message formatting, the
score-to-decision thresholds, and collector parsing against mocked API responses (no live network calls
in tests, so `pytest` works the same in CI as it does here).

## 4. Tuning

Everything behavioral lives in `config/preferences.json` — no code changes needed to adjust:

- `roles.include` / `roles.exclude_keywords` — the soft title pre-filter (a title not on the include
  list still reaches the AI unless it hits an exclude keyword — see `backend/filters/role.py`)
- `experience.hard_reject_years` (default 7), `reject_seniority_titles`, `seniority_title_exceptions`
  (e.g. "Senior QA" is allowed through since QA seniority ladders differ from PM ones)
- `location.tier_a_worldwide_keywords` / `tier_b_africa_emea_keywords` / `tier_d_reject_keywords`
- `scoring.min_score_to_send_immediate` (default 85) / `min_score_to_send_digest` (default 70)
- `sources.greenhouse_boards` / `sources.lever_companies` — add company board tokens/slugs here to pull
  directly from their ATS (see below)

`config/candidate_profile.json` is the evidence the AI actually reasons from — update it as your resume
or portfolio changes; it's structured, not just pasted text, so the matcher can cite specific case
studies (e.g. the AI-feature-shipping work at Composity, the 0-to-1 roadmap work at Bravura) rather than
matching on keywords alone.

## 5. Sources

| Source | How | Notes |
|---|---|---|
| RemoteOK | public API | |
| Remotive | public API | queried by category (product, QA, project-management, ...) |
| We Work Remotely | RSS | uses the `<region>` field as the eligibility signal when present |
| Himalayas | public API | uses `locationRestrictions` as the eligibility signal when present |
| Greenhouse | public per-company API | add board tokens to `sources.greenhouse_boards` |
| Lever | public per-company API | add company slugs to `sources.lever_companies` |
| Wellfound | **manual import** | see below |
| LinkedIn | discovery links only | see below |

**Wellfound**: it has no public jobs API and its listings sit behind a logged-in session with
anti-scraping protection, so this project deliberately does not scrape it. Instead,
`backend/collectors/wellfound.py` reads `data/wellfound_manual.json` if you create it — a plain JSON
list of `{title, company, url, location, hires_remotely_from, description}` objects for postings you
copy over yourself (Wellfound's "Hires Remotely From" field is exactly the eligibility signal worth
preserving when you do). It's a no-op, not an error, when that file doesn't exist.

**LinkedIn**: `backend/collectors/linkedin_discovery.py` only builds LinkedIn's own search URLs per
target role (`build_search_links`) — discovery, never scraping. It's not wired into AI scoring since
there's no posting text to evaluate until you open the real listing.

## 6. Repo layout

```
backend/
  collectors/     one file per job source, all normalize into backend.models.Job
  filters/        deterministic hard filters: role, location, experience, job_type, company_quality
  matching/       candidate profile rendering + the scoring engine (Gemini and Anthropic backends)
  notifications/  Discord webhook formatting + sending
  storage/        data/jobs.json persistence, dedup, stats
  pipeline.py     orchestrates one full run
  app.py          FastAPI serving the dashboard + /api/jobs, /api/stats
frontend/dashboard/index.html   single-file dashboard (Tailwind CDN, no build step)
config/           candidate_profile.json + preferences.json — the only two files most tuning touches
data/jobs.json    the job store (committed by the scheduled run so the dashboard always has current data)
tests/            pytest suite, no live network calls
.github/workflows/job-agent.yml   the twice-daily scheduled run
```
