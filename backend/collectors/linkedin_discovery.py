"""LinkedIn + board discovery helpers.

By design this never scrapes LinkedIn (or other discovery-only boards). It builds
public search / category URLs for the dashboard Discovery panel.
"""
from __future__ import annotations

from urllib.parse import urlencode

LINKEDIN_BASE = "https://www.linkedin.com/jobs/search/"

BOARD_LINKS = [
    # Live collectors (also linked for manual browsing)
    {"name": "RemoteOK", "url": "https://remoteok.com/remote-product-jobs", "note": "Live collector"},
    {"name": "Remotive", "url": "https://remotive.com/remote-jobs/product", "note": "Live collector"},
    {"name": "We Work Remotely", "url": "https://weworkremotely.com/categories/remote-product-jobs", "note": "Live collector"},
    {"name": "Himalayas", "url": "https://himalayas.app/jobs/product-manager", "note": "Live collector"},
    {"name": "Jobicy", "url": "https://jobicy.com/?remote_job_category=product", "note": "Live collector"},
    {"name": "Mind the Product", "url": "https://www.mindtheproduct.com/jobs/", "note": "Live collector"},
    {"name": "Arbeitnow", "url": "https://www.arbeitnow.com/jobs?keywords=product+manager", "note": "Live collector"},
    {"name": "Working Nomads", "url": "https://www.workingnomads.com/jobs", "note": "Live collector"},
    {"name": "Remote First Jobs", "url": "https://remotefirstjobs.com/remote-jobs/product", "note": "Live collector"},
    {"name": "NoDesk", "url": "https://nodesk.co/remote-jobs/", "note": "Live collector"},
    {"name": "Jobspresso", "url": "https://jobspresso.co/", "note": "Live collector"},
    {"name": "4 Day Week", "url": "https://4dayweek.io/remote", "note": "Live collector"},
    # Manual import / discovery
    {"name": "Wellfound", "url": "https://wellfound.com/jobs", "note": "Manual import → data/wellfound_manual.json"},
    {"name": "The SaaS Jobs", "url": "https://thesaasjobs.com/", "note": "Manual import → data/thesaasjobs_manual.json"},
    {"name": "Startup Jobs", "url": "https://startup.jobs/", "note": "Manual import → data/startupjobs_manual.json"},
    {"name": "JustRemote", "url": "https://justremote.co/remote-jobs", "note": "Discovery — no public API"},
    {"name": "Dynamite Jobs", "url": "https://dynamitejobs.com/", "note": "Discovery — API needs key"},
    {"name": "DailyRemote", "url": "https://dailyremote.com/", "note": "Discovery"},
    {"name": "Hiring Cafe", "url": "https://hiring.cafe/", "note": "Discovery — ATS aggregator"},
    {"name": "Jobgether", "url": "https://jobgether.com/", "note": "Discovery"},
    {"name": "WeLoveProduct", "url": "https://welove.tech/", "note": "Discovery — product-focused"},
    {"name": "Product Manager Job Board", "url": "https://productmanagerjobboard.com/", "note": "Discovery"},
    {"name": "Uxcel Jobs", "url": "https://uxcel.com/jobs", "note": "Discovery"},
    {"name": "Workello", "url": "https://workello.com/", "note": "Discovery — PM meta-board"},
    {"name": "TestDevJobs", "url": "https://testdevjobs.com/", "note": "Discovery — QA/testing"},
    {"name": "Built In (remote QA)", "url": "https://builtin.com/jobs/remote/dev-engineering/qa", "note": "Discovery — often US-heavy"},
    {"name": "Work at a Startup (YC)", "url": "https://www.workatastartup.com/", "note": "Discovery — YC companies"},
    {"name": "Underdog.io", "url": "https://underdog.io/", "note": "Discovery"},
    {"name": "Otta / Welcome to the Jungle", "url": "https://app.welcometothejungle.com/", "note": "Discovery — UK/EU skew"},
    {"name": "Remote100K", "url": "https://remote100k.com/", "note": "Discovery — $100k+ filter"},
    {"name": "Arc", "url": "https://arc.dev/remote-jobs", "note": "Discovery — vetted senior"},
    {"name": "FlexJobs", "url": "https://www.flexjobs.com/", "note": "Paid board — browse manually"},
    {"name": "PowerToFly", "url": "https://powertofly.com/jobs", "note": "Discovery — DEI-focused"},
    {"name": "Virtual Vocations", "url": "https://www.virtualvocations.com/", "note": "Paid board — browse manually"},
]


def build_search_links(roles: list[str], remote_only: bool = True, limit: int = 12) -> list[dict]:
    links = []
    for role in roles[:limit]:
        params: dict[str, str] = {"keywords": role}
        if remote_only:
            params["f_WT"] = "2"
        links.append({"role": role, "url": f"{LINKEDIN_BASE}?{urlencode(params)}"})
    return links


def build_discovery(roles: list[str], remote_only: bool = True) -> dict:
    return {
        "linkedin": build_search_links(roles, remote_only=remote_only),
        "boards": BOARD_LINKS,
    }
