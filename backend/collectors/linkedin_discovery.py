"""Discovery and external board links manager for CareerOS.

Contains curated remote job boards, ATS job sites, specialized tech/product boards,
and direct LinkedIn search query builders.
"""
from __future__ import annotations

from urllib.parse import urlencode

LINKEDIN_BASE = "https://www.linkedin.com/jobs/search/"

BOARD_LINKS = [
    # -------------------------------------------------------------------------
    # 1. Live Collectors (API / RSS / Automated Ingestion)
    # -------------------------------------------------------------------------
    {"name": "RemoteOK", "url": "https://remoteok.com/remote-product-jobs", "category": "Live API", "note": "Automated ingestion via public API"},
    {"name": "Remotive", "url": "https://remotive.com/remote-jobs/product", "category": "Live API", "note": "Automated ingestion via category queries"},
    {"name": "We Work Remotely", "url": "https://weworkremotely.com/categories/remote-product-jobs", "category": "Live RSS", "note": "Automated RSS ingestion with region detection"},
    {"name": "Himalayas", "url": "https://himalayas.app/jobs/product-manager", "category": "Live API", "note": "Automated API ingestion with location restrictions"},
    {"name": "Jobicy", "url": "https://jobicy.com/?remote_job_category=product", "category": "Live API", "note": "Automated API ingestion for remote product roles"},
    {"name": "Mind the Product", "url": "https://www.mindtheproduct.com/jobs/", "category": "Live JSON", "note": "Automated ingestion of product-specialized board"},
    {"name": "Arbeitnow", "url": "https://www.arbeitnow.com/jobs?keywords=product+manager", "category": "Live API", "note": "Automated ingestion for tech & PM roles"},
    {"name": "Working Nomads", "url": "https://www.workingnomads.com/jobs", "category": "Live API", "note": "Automated ingestion via exposed API"},
    {"name": "Remote First Jobs", "url": "https://remotefirstjobs.com/remote-jobs/product", "category": "Live RSS", "note": "Automated RSS ingestion for product roles"},
    {"name": "NoDesk", "url": "https://nodesk.co/remote-jobs/", "category": "Live RSS", "note": "Automated RSS ingestion"},
    {"name": "Jobspresso", "url": "https://jobspresso.co/", "category": "Live RSS", "note": "Automated RSS feed ingestion"},
    {"name": "4 Day Week", "url": "https://4dayweek.io/remote", "category": "Live API", "note": "Automated API for remote 4-day & flexible roles"},
    {"name": "Remote Woman", "url": "https://remotewoman.com/", "category": "Live RSS", "note": "Automated RSS ingestion for remote-first roles"},
    {"name": "AI Jobs", "url": "https://theaijobboard.com/", "category": "Live RSS", "note": "Automated ingestion for AI & machine learning product roles"},
    {"name": "JS Remotely", "url": "https://jsremotely.com/", "category": "Live API", "note": "Automated ingestion for tech & product roles"},
    {"name": "Remote Rocketship", "url": "https://www.remoterocketship.com/remote-jobs/", "category": "Live API", "note": "Ingested when REMOTE_ROCKETSHIP_API_KEY is configured"},

    # -------------------------------------------------------------------------
    # 2. ATS Direct Integrations (Company Board Endpoints)
    # -------------------------------------------------------------------------
    {"name": "Greenhouse Boards", "url": "https://boards.greenhouse.io", "category": "ATS Board", "note": "Direct ATS boards: Intercom, Miro, Duolingo, Calendly, GitLab, HashiCorp"},
    {"name": "Lever Boards", "url": "https://jobs.lever.co", "category": "ATS Board", "note": "Direct ATS boards: Netflix, Spotify, Shopify"},
    {"name": "Ashby Boards", "url": "https://jobs.ashbyhq.com", "category": "ATS Board", "note": "Direct ATS boards: Notion, Linear, Ramp, Vercel"},

    # -------------------------------------------------------------------------
    # 3. User-Requested Remote Job Portals & Aggregators
    # -------------------------------------------------------------------------
    {"name": "Jobgether", "url": "https://jobgether.com/", "category": "Remote Portal", "note": "Smart remote job aggregator with verified remote filters"},
    {"name": "PowerToFly", "url": "https://powertofly.com/jobs?location=Remote", "category": "Remote Portal", "note": "Remote tech and product roles with DEI emphasis"},
    {"name": "RemoteHub", "url": "https://remotehub.io/", "category": "Remote Portal", "note": "Worldwide remote tech, product, and management jobs"},
    {"name": "Remote Work Hub", "url": "https://remoteworkhub.com/", "category": "Remote Portal", "note": "Curated remote job directory across global teams"},
    {"name": "Remote Jobs Club", "url": "https://remotejobsclub.com/", "category": "Newsletter / Board", "note": "Weekly curated remote opportunities"},
    {"name": "CloudPeeps", "url": "https://cloudpeeps.com/", "category": "Freelance / Contract", "note": "Freelance, contract, and community product roles"},
    {"name": "WordPress Jobs", "url": "https://jobs.wordpress.net/", "category": "Specialized Tech", "note": "Open-source, ecosystem, and product roles"},
    {"name": "Simply Communicate Jobs", "url": "https://simply-communicate.com/jobs/", "category": "Internal Comms / Ops", "note": "Internal communications and product operations roles"},
    {"name": "Virtual Assistant Jobs", "url": "https://virtualassistantjobs.com/", "category": "Remote Operations", "note": "Operations and coordination positions"},
    {"name": "OutsourcingJobs.ph", "url": "https://outsourcingjobs.ph/", "category": "Remote Operations", "note": "Global remote staffing and project roles"},
    {"name": "Remotive.io", "url": "https://remotive.io/", "category": "Remote Portal", "note": "Alternative domain for Remotive global remote jobs"},
    {"name": "Jobmote", "url": "https://jobmote.com/", "category": "Remote Portal", "note": "Aggregator of 100% remote product and engineering jobs"},
    {"name": "RemoteBaba", "url": "https://remotebaba.com/", "category": "Remote Portal", "note": "Global remote job search engine"},
    {"name": "Idealist (Remote)", "url": "https://www.idealist.org/en/jobs?remoteMode=YES", "category": "Social Impact / NGO", "note": "Remote product and operational roles in social impact & tech"},
    {"name": "RemoteJobr", "url": "https://remotejobr.com/", "category": "Remote Portal", "note": "Curated remote listings for developers and PMs"},
    {"name": "Jobscribe", "url": "https://jobscribe.com/", "category": "Newsletter / Board", "note": "Daily remote tech job alerts"},
    {"name": "Remote Hunt", "url": "https://remotehunt.com/", "category": "Company Directory", "note": "Remote-first companies directory and job aggregator"},
    {"name": "Outsourcing Insight", "url": "https://outsourcinginsight.com/", "category": "Remote Ops / Agency", "note": "Outsourcing directory and global talent opportunities"},
    {"name": "GoRemote", "url": "https://goremote.io/", "category": "Remote Portal", "note": "Global remote opportunities"},
    {"name": "Dynamite Jobs", "url": "https://dynamitejobs.com/remote-product-jobs", "category": "Remote Portal", "note": "Remote entrepreneurial, product, and tech roles"},
    {"name": "The Muse (Remote)", "url": "https://www.themuse.com/jobs?filter=remote", "category": "Curated Portal", "note": "Remote roles at modern tech and venture-backed companies"},
    {"name": "Awesome Jobs", "url": "https://awesomejobs.io/", "category": "Curated Board", "note": "Vetted opportunities across product and engineering"},
    {"name": "TechJobs (Remote)", "url": "https://techjobs.com/", "category": "Tech Board", "note": "Global technology career portal"},
    {"name": "Laravel Jobs", "url": "https://jobs.laravel.io/", "category": "Specialized Tech", "note": "Roles in web SaaS ecosystems"},
    {"name": "Jobs in Pods", "url": "https://jobsinpods.com/", "category": "Podcast / Media", "note": "Audio job briefs and company showcases"},
    {"name": "Ruby Now Jobs", "url": "https://rubynow.com/", "category": "Specialized Tech", "note": "Web SaaS and product engineering"},
    {"name": "Remoters", "url": "https://remoters.net/jobs/", "category": "Remote Community", "note": "Digital nomad and remote career portal"},
    {"name": "Outsourcely", "url": "https://outsourcely.com/", "category": "Remote Staffing", "note": "Remote startup hires and full-time contracts"},
    {"name": "Crossover", "url": "https://crossover.com/", "category": "Global Talent", "note": "High-compensation 100% remote global positions"},
    {"name": "Remote Jobs", "url": "https://remotejobs.com/", "category": "Remote Portal", "note": "Direct remote listings across all disciplines"},

    # -------------------------------------------------------------------------
    # 4. Startup & Venture Ecosystems
    # -------------------------------------------------------------------------
    {"name": "Wellfound", "url": "https://wellfound.com/jobs", "category": "Startup / YC", "note": "Startup and early-stage PM roles (Manual import available)"},
    {"name": "The SaaS Jobs", "url": "https://thesaasjobs.com/", "category": "B2B SaaS", "note": "Dedicated to B2B SaaS positions (Manual import available)"},
    {"name": "Startup Jobs", "url": "https://startup.jobs/", "category": "Startup Ecosystem", "note": "Cloudflare-gated startup board (Manual import available)"},
    {"name": "Work at a Startup (YC)", "url": "https://www.workatastartup.com/", "category": "Startup / YC", "note": "Y Combinator portfolio companies"},
    {"name": "Hiring Cafe", "url": "https://hiring.cafe/", "category": "ATS Aggregator", "note": "Scrapes Greenhouse, Lever, and Workday directly"},
    {"name": "Otta / Welcome to the Jungle", "url": "https://app.welcometothejungle.com/", "category": "Curated Portal", "note": "Fast-growing global startups"},
    {"name": "Underdog.io", "url": "https://underdog.io/", "category": "Curated Network", "note": "Curated talent batch for top tech startups"},
    {"name": "TestDevJobs", "url": "https://testdevjobs.com/", "category": "QA / Testing", "note": "Discovery — QA/testing"},
    {"name": "JustRemote", "url": "https://justremote.co/remote-jobs", "category": "Remote Portal", "note": "Hidden remote jobs platform"},
]


def build_search_links(roles: list[str], remote_only: bool = True, limit: int = 12) -> list[dict]:
    links = []
    for role in roles[:limit]:
        params: dict[str, str] = {"keywords": role}
        if remote_only:
            params["f_WT"] = "2"  # Remote filter in LinkedIn
        links.append({"role": role, "url": f"{LINKEDIN_BASE}?{urlencode(params)}"})
    return links


def build_discovery(roles: list[str], remote_only: bool = True) -> dict:
    return {
        "linkedin": build_search_links(roles, remote_only=remote_only),
        "boards": BOARD_LINKS,
        "total_boards_count": len(BOARD_LINKS),
    }
