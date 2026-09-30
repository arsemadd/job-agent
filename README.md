# CareerOS (formerly Job Matcher) 🚀

**Personal Job Search & Career Operating System for Remote Product Management & QA Roles**  
Designed for **Arsema Doji Wordofa** (Product Manager & Software Engineer, 3+ yrs experience, 100% Remote, English-only, target: PM / Technical PM / AI PM).

```
Job Discovery (31+ Boards) → Hard Filters → AI Match Scoring (Gemini/Anthropic) 
  ↓
Discord Webhook Alerts (85+ Immediate / 65+ Digest)
  ↓
CareerOS Application Lifecycle (Draft Cover Letter → Tailor & Diff → 1-Click Track → Interview → Outcome)
```

---

## 🌟 What's New in CareerOS

CareerOS evolves the simple job-matching script into a complete, end-to-end career workflow:

1. **Discord Alerts Center & 1-Click Tracking**:
   - Every role sent to your Discord webhook appears in the dedicated **Discord Alerts** dashboard section.
   - Direct external **Apply** link opens the original posting in one click.
   - Click **"Track as Applied"** to immediately record the application, advance its status, and set up an automated 7-day follow-up reminder.
2. **End-to-End Application Lifecycle**:
   - Status pipeline: `DISCOVERED` → `SHORTLISTED` → `PREPARING` → `APPLIED` → `SCREENING` → `INTERVIEWING` → `OFFER` / `ARCHIVED`.
   - Kanban board and table views with quick-filtering.
3. **Grounded AI Application Strategy & Cover Letter Generator**:
   - Auto-generates tailored application strategies grounded in Arsema's authentic portfolio (Bravura Healthcare EHR, Composity ERP, Ethiojobs, AAU Software Engineering B.Sc.).
   - Drafts role-specific cover letters, strategic angles, and custom Q&A answers.
4. **Document Versioning & Visual Diff Engine**:
   - Compare draft cover letters vs tailored versions with git-style line/word addition and deletion highlights.
   - Stores exact submission snapshots (resume version, cover letter copy, questions & answers, portfolio links).
5. **31+ Curated Remote Job Boards + Jobgether**:
   - Includes Jobgether, PowerToFly, RemoteWoman, RemoteHub, RemoteWorkHub, RemoteJobsClub, CloudPeeps, WordPress Jobs, Simply Communicate, VirtualAssistantJobs, OutsourcingJobs, Jobmote, RemoteBaba, Idealist, RemoteJobr, JobScribe, RemoteHunt, OutsourcingInsight, GoRemote, DynamiteJobs, TheMuse, AwesomeJobs, TechJobs, LaravelJobs, JobsinPods, RubyNow, Remoters, Outsourcely, Crossover, RemoteJobs.com, and more.
6. **SQLite Relational Store (`data/careeros.db`)**:
   - Automatically migrates existing jobs from `data/jobs.json`.
   - Backed by relational tables for jobs, applications, cover letters, resume versions, interviews, tasks, and activity logs.

---

## 🛠️ Tech Stack

| Layer | Choice |
|---|---|
| Pipeline | Python 3.12 |
| AI Model | Gemini 2.5 Flash / Flash Lite (`google-genai`) or Anthropic Claude |
| Backend API | FastAPI + SQLite (`data/careeros.db`) + Background Scheduler |
| Frontend | Vanilla HTML5 + Tailwind CSS (Responsive Single-Page App) |
| Alerts | Discord Webhook Notifications (Forum & Text Channels) |
| Container | Dockerfile, Render Blueprint (`render.yaml`), Procfile |

---

## 🚀 Quick Start (Local Run)

### 1. Prerequisites & Virtual Environment
```bash
# Clone the repository
git clone https://github.com/arsemadd/job-agent.git
cd job-agent

# Create & activate virtual environment
python -m venv .venv
.venv\Scripts\activate      # On Windows
source .venv/bin/activate   # On Linux/macOS

# Install dependencies
pip install -r requirements-dev.txt
```

### 2. Configure Environment (`.env`)
Create a `.env` file based on `.env.example`:
```env
AI_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
DISCORD_WEBHOOK_URL=https://discordapp.com/api/webhooks/your_webhook_id/your_webhook_token
GEMINI_MODEL=gemini-3.5-flash-lite
DISCORD_FORUM=0
DISCORD_NOTIFY_EMPTY_RUNS=1
ENABLE_BACKGROUND_SCHEDULER=1
```

### 3. Run CareerOS Dashboard
```bash
python run_careeros.py
```
This opens the CareerOS Dashboard automatically at **http://127.0.0.1:8000** (API docs at **http://127.0.0.1:8000/docs**).

---

## ☁️ Deployment Guide (Keep Running 24/7 in Cloud)

Because CareerOS includes both an interactive web dashboard and a persistent SQLite database, standard static hosts like Netlify (which only host client-side assets) cannot keep a Python server and database running.

Here are the easiest recommended options to keep CareerOS running 24/7:

### Option A: Render.com (Recommended Free/Low Cost)
1. Push code to your GitHub repo.
2. Sign up at [Render.com](https://render.com) and click **New → Web Service**.
3. Select your GitHub repository `arsemadd/job-agent`.
4. Render automatically detects `render.yaml` or you can specify:
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn backend.app:app --host 0.0.0.0 --port $PORT`
5. Under **Environment Variables**, add:
   - `GEMINI_API_KEY`
   - `DISCORD_WEBHOOK_URL`
   - `ENABLE_BACKGROUND_SCHEDULER=1`
   - `DISCORD_FORUM=0`
6. Click **Deploy**. Your app will be live 24/7 at `https://careeros-xxxx.onrender.com`!

### Option B: GitHub Actions (Free Hourly Cron)
- The repo already includes `.github/workflows/job-agent.yml` which executes the sourcing pipeline hourly, sends Discord alerts, and commits new jobs back to the repository.
- Ensure your repository Secrets contain:
  - `GEMINI_API_KEY`
  - `DISCORD_WEBHOOK_URL`

### Option C: Docker Container
```bash
docker build -t careeros:latest .
docker run -d -p 8000:8000 --env-file .env careeros:latest
```

---

## 🧪 Testing

Run the full automated test suite (85+ tests):
```bash
pytest tests/
```

---

## 🔒 Configuration & Candidate Profile

- `config/candidate_profile.json`: Contains Arsema's projects (Bravura EHR, Composity ERP), skills, education, and target job criteria.
- `config/preferences.json`: Strict filtering rules:
  - `language.reject_non_english_requirements`: True (rejects any jobs requiring French, German, Spanish, etc.)
  - `location.require_fully_remote`: True (rejects hybrid and on-site)
  - `experience.hard_reject_years`: Rejects roles demanding >6 years of experience.
  - `scoring.min_score_to_send_immediate`: 85
  - `scoring.min_score_to_send_digest`: 65

---

## 📜 License
Private personal project for Arsema Doji Wordofa.
