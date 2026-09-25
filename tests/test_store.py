import json
import os

from backend.storage.store import JobStore


def test_upsert_and_persist_roundtrip(tmp_path):
    path = os.path.join(tmp_path, "jobs.json")
    store = JobStore(path)
    store.upsert("key1", {"title": "PM", "company": "Acme", "score": 90, "status": "sent", "hard_filter_passed": True, "decision": "SEND"})
    store.save()

    store2 = JobStore(path)
    assert store2.seen("key1")
    assert store2.get("key1")["title"] == "PM"
    assert store2.already_notified_identity("Acme", "PM") is True


def test_seen_prevents_duplicate_processing(tmp_path):
    store = JobStore(os.path.join(tmp_path, "jobs.json"))
    assert store.seen("nope") is False
    store.upsert("nope", {"title": "X", "company": "Y"})
    assert store.seen("nope") is True
    assert store.seen_identity("Y", "X") is True


def test_identity_blocks_same_company_title_under_new_key(tmp_path):
    store = JobStore(os.path.join(tmp_path, "jobs.json"))
    store.upsert("oldkey", {
        "title": "AI Product Manager",
        "company": "Moebel De",
        "status": "sent",
        "notified_at": "2026-09-20T00:00:00+00:00",
    })
    assert store.already_notified_identity("Moebel De", "AI Product Manager") is True
    assert store.seen_identity("Moebel De", "AI Product Manager") is True


def test_prune_drops_old_rejects_keeps_sent(tmp_path):
    path = os.path.join(tmp_path, "jobs.json")
    store = JobStore(path)
    store.upsert("sent1", {
        "title": "PM", "company": "A", "status": "sent",
        "hard_filter_passed": True, "description": "keep me " * 100,
    })
    store.upsert("rej1", {
        "title": "Eng", "company": "B", "status": "rejected",
        "hard_filter_passed": False, "description": "drop body " * 200,
        "first_seen_at": "2020-01-01T00:00:00+00:00",
        "last_seen_at": "2020-01-01T00:00:00+00:00",
    })
    removed = store.prune(rejected_retention_days=1, keep_rejected_max=0)
    assert removed >= 1
    assert store.seen("sent1")
    assert not store.seen("rej1")
    store.save(prune_first=False)
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    assert "drop body" not in raw


def test_corrupt_file_recovers_instead_of_crashing(tmp_path):
    path = os.path.join(tmp_path, "jobs.json")
    with open(path, "w") as f:
        f.write("{not valid json")
    store = JobStore(path)  # should not raise
    assert store.all() == []


def test_stats_computation(tmp_path):
    store = JobStore(os.path.join(tmp_path, "jobs.json"))
    store.upsert("a", {"hard_filter_passed": True, "decision": "SEND", "status": "sent", "score": 90, "title": "a", "company": "c"})
    store.upsert("b", {"hard_filter_passed": True, "decision": "DIGEST", "status": "digest_sent", "score": 75, "title": "b", "company": "c"})
    store.upsert("c", {"hard_filter_passed": False, "decision": "REJECT", "status": "rejected", "score": None, "title": "c", "company": "c"})
    s = store.stats()
    assert s["jobs_found"] == 3
    assert s["passed_filters"] == 2
    assert s["strong_matches"] == 1
    assert s["digest_matches"] == 1
    assert s["sent_to_discord"] == 2
    assert s["average_match"] == 82.5
