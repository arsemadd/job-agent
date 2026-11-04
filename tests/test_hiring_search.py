from backend.collectors.hiring_search import (
    build_hiring_search_pack,
    google_search_url,
    score_hiring_lead,
    HiringSearchCollector,
)


def test_google_search_url_encodes_site_query():
    url = google_search_url('site:linkedin.com/posts "Product Manager" hiring remote')
    assert "google.com/search" in url
    assert "linkedin.com" in url
    assert "qdr" in url


def test_hiring_search_pack_has_routine_sections(prefs_path_ok=True):
    pack = build_hiring_search_pack({})
    assert pack["google_searches"]
    assert pack["linkedin_post_searches"]
    assert pack["people_searches"]
    assert pack["formal_vacancy_searches"]
    assert "B2B SaaS" in " ".join(pack["industries_monitored"])
    assert pack["automation"]["live_fetch"] is False


def test_score_hiring_lead_strong_remote_pm():
    score, why, gaps = score_hiring_lead(
        "Founder at Acme — hiring Product Manager (remote)",
        "We're hiring a Product Manager for our B2B SaaS. Fully remote worldwide.",
    )
    assert score >= 70
    assert why


def test_score_hiring_lead_rejects_us_only():
    score, why, gaps = score_hiring_lead(
        "Hiring Product Manager",
        "US only. Must be based in the United States.",
    )
    assert score == 0
    assert gaps


def test_hiring_search_collector_skips_without_api_key(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    monkeypatch.delenv("SERPAPI_KEY", raising=False)
    jobs = HiringSearchCollector({"hiring_search": {"enabled": True}}).fetch()
    assert jobs == []
