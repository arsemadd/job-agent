from backend.collectors.hiring_search import (
    build_hiring_search_pack,
    google_search_url,
    score_hiring_lead,
    HiringSearchCollector,
    _row_to_job,
)


def test_google_search_url_encodes_site_query():
    url = google_search_url('site:linkedin.com/posts "Product Manager" hiring remote')
    assert "google.com/search" in url
    assert "linkedin.com" in url
    assert "qdr" in url


def test_hiring_search_pack_has_routine_sections():
    pack = build_hiring_search_pack({})
    assert pack["google_searches"]
    assert pack["linkedin_post_searches"]
    assert pack["people_searches"]
    assert pack["formal_vacancy_searches"]
    assert "B2B SaaS" in " ".join(pack["industries_monitored"])
    assert pack["automation"]["live_fetch"] is False


def test_score_hiring_lead_strong_worldwide_pm():
    score, why, gaps = score_hiring_lead(
        "Founder at Acme — hiring Product Manager",
        "We're hiring a Product Manager for our B2B SaaS. Fully remote worldwide. 3-5 years.",
    )
    assert score >= 70
    assert why


def test_score_hiring_lead_rejects_us_only():
    score, why, gaps = score_hiring_lead(
        "Hiring Product Manager remote",
        "Remote US only. Must be based in the United States. Work from anywhere in the world — wait no, US.",
    )
    assert score == 0
    assert any("Country-restricted" in g or "worldwide" in g.lower() for g in gaps)


def test_score_hiring_lead_rejects_remote_without_worldwide():
    score, why, gaps = score_hiring_lead(
        "Hiring Product Manager",
        "Remote role. We're hiring a Product Manager.",
    )
    assert score == 0
    assert gaps


def test_score_hiring_lead_rejects_ten_years():
    score, why, gaps = score_hiring_lead(
        "Hiring Product Manager worldwide",
        "Work from anywhere. Looking for 10+ years of product experience.",
    )
    assert score == 0
    assert any("years" in g.lower() for g in gaps)


def test_score_hiring_lead_rejects_senior_title():
    score, why, gaps = score_hiring_lead(
        "Senior Product Manager — remote worldwide",
        "Hiring Senior Product Manager. Work from anywhere. 5 years.",
    )
    assert score == 0


def test_score_hiring_lead_allows_five_years_worldwide():
    score, why, gaps = score_hiring_lead(
        "Product Manager",
        "We're hiring. Remote worldwide. 3-5 years of experience.",
    )
    assert score >= 70


def test_row_to_job_drops_us_remote():
    job = _row_to_job(
        {
            "title": "Hiring Product Manager",
            "link": "https://www.linkedin.com/posts/abc",
            "snippet": "Remote US. Product Manager role.",
        },
        "q",
    )
    assert job is None


def test_row_to_job_keeps_worldwide():
    job = _row_to_job(
        {
            "title": "Founder at Acme hiring Product Manager",
            "link": "https://www.linkedin.com/posts/abc",
            "snippet": "We're hiring a Product Manager. Work from anywhere worldwide. 4 years.",
        },
        "q",
    )
    assert job is not None
    assert "Worldwide" in job.location_raw


def test_hiring_search_collector_skips_without_api_key(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    jobs = HiringSearchCollector({"hiring_search": {"enabled": True}}).fetch()
    assert jobs == []
