from backend.notifications.discord import (
    DISCORD_CONTENT_LIMIT,
    format_digest_embed,
    format_immediate_message,
)


SAMPLE_RECORD = {
    "score": 91,
    "title": "Product Manager - AI SaaS",
    "company": "XYZ",
    "location_raw": "Remote - Worldwide",
    "years_required_display": "2-4 years",
    "why_matches": ["SaaS experience", "AI feature experience", "Agile/Jira"],
    "gaps": ["No direct fintech experience"],
    "url": "https://example.com/apply/1",
    "source": "wellfound",
    "posted_at": None,
}


def test_immediate_message_contains_key_fields():
    msg = format_immediate_message(SAMPLE_RECORD)
    assert "91%" in msg
    assert "XYZ" in msg
    assert "Product Manager - AI SaaS".upper() in msg
    assert "https://example.com/apply/1" in msg
    assert "SaaS experience" in msg
    assert "No direct fintech experience" in msg
    assert "wellfound" in msg


def test_immediate_message_under_discord_limit():
    huge = dict(SAMPLE_RECORD)
    huge["why_matches"] = ["x" * 500] * 10
    huge["gaps"] = ["y" * 500] * 10
    msg = format_immediate_message(huge)
    assert len(msg) <= DISCORD_CONTENT_LIMIT


def test_immediate_message_no_gaps_still_renders():
    record = dict(SAMPLE_RECORD)
    record["gaps"] = []
    msg = format_immediate_message(record)
    assert "None noted" in msg


def test_digest_embed_shape():
    embed = format_digest_embed(SAMPLE_RECORD)
    assert "XYZ" in embed["description"]
    assert embed["url"] == SAMPLE_RECORD["url"]
    assert isinstance(embed["color"], int)
