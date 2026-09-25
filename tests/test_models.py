from backend.models import Job, identity_key


def test_dedup_key_stable_for_identical_job():
    j1 = Job(source="remoteok", external_id="1", title="Product Manager", company="Acme", url="https://x.com/1")
    j2 = Job(source="remotive", external_id="99", title="Product Manager", company="Acme", url="https://x.com/1")
    assert j1.dedup_key == j2.dedup_key


def test_dedup_key_same_company_title_ignores_url_churn():
    # Boards often rotate URL IDs for the same posting — must not re-alert.
    j1 = Job(source="arbeitnow", external_id="1", title="AI Product Manager", company="Moebel De",
             url="https://www.arbeitnow.com/view/product-manager-ai-search-hamburg-167397")
    j2 = Job(source="arbeitnow", external_id="2", title="AI Product Manager", company="Moebel De",
             url="https://www.arbeitnow.com/view/product-manager-ai-search-hamburg-292991")
    assert j1.dedup_key == j2.dedup_key
    assert j1.identity_key == j2.identity_key
    assert identity_key("Moebel De", "AI Product Manager") == j1.identity_key


def test_dedup_key_differs_for_different_title():
    j1 = Job(source="remoteok", external_id="1", title="Product Manager", company="Acme", url="https://x.com/1")
    j2 = Job(source="remoteok", external_id="2", title="QA Engineer", company="Acme", url="https://x.com/1")
    assert j1.dedup_key != j2.dedup_key


def test_dedup_key_ignores_query_string():
    j1 = Job(source="remoteok", external_id="1", title="PM", company="Acme", url="https://x.com/job?utm_source=rss")
    j2 = Job(source="remoteok", external_id="1", title="PM", company="Acme", url="https://x.com/job?utm_source=twitter")
    assert j1.dedup_key == j2.dedup_key


def test_html_stripped_from_description_on_construction():
    j = Job(source="s", external_id="1", title="T", company="C", url="u", description="<p>Hello <b>world</b></p>")
    assert "<" not in j.description
    assert "Hello world" in j.description


def test_to_dict_from_dict_roundtrip():
    j = Job(source="s", external_id="1", title="T", company="C", url="u", tags=["a", "b"])
    d = j.to_dict()
    assert d["dedup_key"] == j.dedup_key
    assert d["identity_key"] == j.identity_key
    j2 = Job.from_dict(d)
    assert j2.dedup_key == j.dedup_key
    assert j2.tags == ["a", "b"]
