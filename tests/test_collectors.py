import responses

from backend.collectors.greenhouse import GreenhouseCollector
from backend.collectors.lever import LeverCollector
from backend.collectors.remoteok import RemoteOKCollector, API_URL as REMOTEOK_URL
from backend.collectors.remotive import RemotiveCollector, API_URL as REMOTIVE_URL
from backend.collectors.weworkremotely import WeWorkRemotelyCollector, FEED_URL as WWR_URL


@responses.activate
def test_remoteok_skips_legal_notice_row():
    responses.add(
        responses.GET, REMOTEOK_URL, json=[
            {"legal": "notice, no id field here"},
            {"id": 1, "position": "Product Manager", "company": "Acme", "url": "https://remoteok.com/1",
             "description": "<p>desc</p>", "location": "Remote", "tags": ["product"], "date": "2026-09-01"},
        ], status=200,
    )
    jobs = RemoteOKCollector().fetch()
    assert len(jobs) == 1
    assert jobs[0].title == "Product Manager"
    assert jobs[0].company == "Acme"


@responses.activate
def test_remoteok_collector_resilient_to_malformed_row():
    responses.add(
        responses.GET, REMOTEOK_URL, json=[
            {"legal": "notice"},
            {"id": 1, "position": "PM", "company": "Acme", "url": "https://x.com/1"},
            {"id": 2},  # missing position -> should be skipped, not crash
        ], status=200,
    )
    jobs = RemoteOKCollector().fetch()
    assert len(jobs) == 1


@responses.activate
def test_remotive_dedupes_across_categories():
    payload = {"jobs": [
        {"id": 42, "title": "QA Analyst", "company_name": "Acme", "url": "https://x.com/42",
         "candidate_required_location": "Worldwide", "description": "d", "tags": []},
    ]}
    for _ in range(5):  # one response per category queried
        responses.add(responses.GET, REMOTIVE_URL, json=payload, status=200)
    jobs = RemotiveCollector().fetch()
    ids = [j.external_id for j in jobs]
    assert ids.count("42") == 1


@responses.activate
def test_weworkremotely_parses_company_title_and_region():
    rss = """<?xml version="1.0"?>
    <rss><channel>
      <item>
        <title>Acme: Senior Product Manager</title>
        <link>https://weworkremotely.com/jobs/123-senior-product-manager</link>
        <description>Job description here</description>
        <region>Anywhere in the World</region>
        <category>Product</category>
        <pubDate>Mon, 01 Sep 2026 00:00:00 +0000</pubDate>
      </item>
    </channel></rss>"""
    responses.add(responses.GET, WWR_URL, body=rss, status=200, content_type="application/rss+xml")
    jobs = WeWorkRemotelyCollector().fetch()
    assert len(jobs) == 1
    assert jobs[0].company == "Acme"
    assert jobs[0].title == "Senior Product Manager"
    assert jobs[0].hires_remotely_from == "Anywhere in the World"


@responses.activate
def test_greenhouse_collector_pulls_configured_boards_only():
    responses.add(
        responses.GET, "https://boards-api.greenhouse.io/v1/boards/acme/jobs",
        json={"jobs": [{"id": 1, "title": "Product Manager", "absolute_url": "https://x.com/1",
                        "content": "desc", "location": {"name": "Remote"}, "updated_at": "2026-09-01"}]},
        status=200,
    )
    jobs = GreenhouseCollector(["acme"]).fetch()
    assert len(jobs) == 1
    assert jobs[0].source == "greenhouse:acme"


def test_greenhouse_collector_noop_when_no_boards_configured():
    assert GreenhouseCollector([]).fetch() == []


@responses.activate
def test_lever_collector_parses_categories():
    responses.add(
        responses.GET, "https://api.lever.co/v0/postings/acme",
        json=[{"id": "abc", "text": "QA Engineer", "hostedUrl": "https://x.com/1",
               "categories": {"location": "Remote", "commitment": "Full-time", "team": "QA"},
               "descriptionPlain": "desc", "createdAt": 1234567890}],
        status=200,
    )
    jobs = LeverCollector(["acme"]).fetch()
    assert len(jobs) == 1
    assert jobs[0].job_type_raw == "Full-time"


def test_lever_collector_noop_when_no_companies_configured():
    assert LeverCollector([]).fetch() == []


@responses.activate
def test_mindtheproduct_parses_list_api():
    from backend.collectors.mindtheproduct import MindTheProductCollector, API_URL

    responses.add(
        responses.GET, API_URL,
        json={
            "jobs": [{
                "id": "abc",
                "slug": "product-manager-xyz",
                "title": "Product Manager",
                "company": "Acme",
                "applicationUrl": "https://acme.example/jobs/1",
                "description": "Build products",
                "location": "Worldwide",
                "remote": True,
                "type": "full-time",
                "publishedAt": "2026-09-01T00:00:00Z",
                "salary": "$100k",
                "tags": [],
                "seniority": "mid",
            }],
            "total": 1,
            "page": 1,
            "pageSize": 50,
            "hasMore": False,
        },
        status=200,
    )
    jobs = MindTheProductCollector().fetch()
    assert len(jobs) == 1
    assert jobs[0].title == "Product Manager"
    assert jobs[0].source == "mindtheproduct"
    assert "Remote" in jobs[0].location_raw


@responses.activate
def test_ashby_collector_skips_unlisted():
    from backend.collectors.ashby import AshbyCollector

    responses.add(
        responses.GET, "https://api.ashbyhq.com/posting-api/job-board/acme",
        json={"jobs": [
            {"id": "1", "title": "Product Manager", "companyName": "Acme",
             "jobUrl": "https://jobs.ashbyhq.com/acme/1", "location": "Remote",
             "isRemote": True, "isListed": True, "publishedAt": "2026-09-01"},
            {"id": "2", "title": "Hidden", "jobUrl": "https://x", "isListed": False},
        ]},
        status=200,
    )
    jobs = AshbyCollector(["acme"]).fetch()
    assert len(jobs) == 1
    assert jobs[0].source == "ashby:acme"


def test_linkedin_discovery_builds_remote_urls():
    from backend.collectors.linkedin_discovery import build_discovery

    data = build_discovery(["Product Manager", "QA Analyst"])
    assert len(data["linkedin"]) == 2
    assert "linkedin.com/jobs/search" in data["linkedin"][0]["url"]
    assert "f_WT=2" in data["linkedin"][0]["url"]
    assert any(b["name"] == "Mind the Product" for b in data["boards"])


@responses.activate
def test_safe_fetch_swallows_collector_exceptions():
    responses.add(responses.GET, REMOTEOK_URL, status=500)
    jobs = RemoteOKCollector().safe_fetch()
    assert jobs == []  # must not raise
