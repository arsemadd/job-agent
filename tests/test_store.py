import json
import os

from backend.storage.store import JobStore


def test_upsert_and_persist_roundtrip(tmp_path):
    path = os.path.join(tmp_path, "jobs.json")
    store = JobStore(path)
    store.upsert("key1", {"title": "PM", "score": 90, "status": "sent", "hard_filter_passed": True, "decision": "SEND"})
    store.save()

    store2 = JobStore(path)
    assert store2.seen("key1")
    assert store2.get("key1")["title"] == "PM"


def test_seen_prevents_duplicate_processing(tmp_path):
    store = JobStore(os.path.join(tmp_path, "jobs.json"))
    assert store.seen("nope") is False
    store.upsert("nope", {"title": "X"})
    assert store.seen("nope") is True


def test_corrupt_file_recovers_instead_of_crashing(tmp_path):
    path = os.path.join(tmp_path, "jobs.json")
    with open(path, "w") as f:
        f.write("{not valid json")
    store = JobStore(path)  # should not raise
    assert store.all() == []


def test_stats_computation(tmp_path):
    store = JobStore(os.path.join(tmp_path, "jobs.json"))
    store.upsert("a", {"hard_filter_passed": True, "decision": "SEND", "status": "sent", "score": 90})
    store.upsert("b", {"hard_filter_passed": True, "decision": "DIGEST", "status": "digest_sent", "score": 75})
    store.upsert("c", {"hard_filter_passed": False, "decision": "REJECT", "status": "rejected", "score": None})
    s = store.stats()
    assert s["jobs_found"] == 3
    assert s["passed_filters"] == 2
    assert s["strong_matches"] == 1
    assert s["digest_matches"] == 1
    assert s["sent_to_discord"] == 2
    assert s["average_match"] == 82.5
