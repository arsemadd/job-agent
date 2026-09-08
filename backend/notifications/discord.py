"""Discord notifier.

Uses an incoming webhook (POST a JSON payload, no persistent bot connection
needed for one-way notifications, per the brief). Two message shapes:

  - send_immediate(): one full-detail message per SEND-tier job (score >=
    scoring.min_score_to_send_immediate), formatted to match the template in
    the brief almost verbatim.
  - send_digest(): a single batched post (Discord embeds, up to 10 per
    message) for DIGEST-tier jobs (the 70-84 band), so a slower day of
    decent-but-not-great matches doesn't spam the channel with full posts.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger("job_agent.discord")

DISCORD_CONTENT_LIMIT = 2000
MAX_EMBEDS_PER_MESSAGE = 10
MAX_ITEMS_IN_LIST = 6


def _score_emoji(score: int) -> str:
    if score >= 85:
        return "🟢"
    if score >= 70:
        return "🟡"
    return "🟠"


def _bullets(items: list[str], marker: str, limit: int = MAX_ITEMS_IN_LIST) -> str:
    items = [i for i in items if i][:limit]
    if not items:
        return f"{marker} (none noted)"
    return "\n".join(f"{marker} {i}" for i in items)


def _relative_time(iso_or_raw: str | None) -> str:
    if not iso_or_raw:
        return "unknown"
    try:
        # posted_at is source-dependent free text/ISO; only attempt relative
        # formatting for clean ISO timestamps, otherwise show as-is.
        dt = datetime.fromisoformat(iso_or_raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)} minutes ago"
        if hours < 48:
            return f"{int(hours)} hours ago"
        return f"{int(hours / 24)} days ago"
    except (ValueError, AttributeError):
        return str(iso_or_raw)


def format_immediate_message(record: dict) -> str:
    score = int(record.get("score", 0))
    emoji = _score_emoji(score)
    title = (record.get("title") or "").upper()
    bar = "━" * 20

    verdict = "Strong match — worth applying" if score >= 85 else "Good match — consider applying"

    body = f"""{bar}
{emoji} {score}% MATCH — {title}
{bar}

Company: {record.get('company', 'Unknown')}
Role: {record.get('title', '')}
Location: {record.get('location_raw') or 'Remote'}
Experience: {record.get('years_required_display', 'not specified')}
Posted: {_relative_time(record.get('posted_at'))}

WHY IT MATCHES
{_bullets(record.get('why_matches', []), '✓')}

GAPS
{_bullets(record.get('gaps', []), '•') if record.get('gaps') else '• None noted'}

VERDICT
{verdict}

🔗 APPLY
{record.get('url', '')}

Source: {record.get('source', 'unknown')}"""

    if len(body) > DISCORD_CONTENT_LIMIT:
        body = body[: DISCORD_CONTENT_LIMIT - 20] + "\n...[truncated]"
    return body


def format_digest_embed(record: dict) -> dict:
    score = int(record.get("score", 0))
    why = ", ".join((record.get("why_matches") or [])[:3]) or "see link"
    gaps = ", ".join((record.get("gaps") or [])[:2]) or "none noted"
    return {
        "title": f"{_score_emoji(score)} {score}% — {record.get('title', '')}",
        "url": record.get("url") or None,
        "description": (
            f"**{record.get('company', 'Unknown')}** · {record.get('location_raw') or 'Remote'}\n"
            f"**Why:** {why}\n**Gaps:** {gaps}"
        ),
        "color": 0x2ECC71 if score >= 80 else 0xF1C40F,
    }


def _post(webhook_url: str, payload: dict, max_retries: int = 3) -> bool:
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(webhook_url, json=payload, timeout=15)
            if resp.status_code == 429:
                retry_after = float(resp.json().get("retry_after", 1))
                time.sleep(retry_after + 0.5)
                continue
            resp.raise_for_status()
            return True
        except requests.RequestException as exc:
            logger.warning("discord post failed (attempt %d/%d): %s", attempt, max_retries, exc)
            time.sleep(1.5 * attempt)
    return False


def send_immediate(record: dict, webhook_url: str) -> bool:
    content = format_immediate_message(record)
    return _post(webhook_url, {"content": content})


def send_digest(records: list[dict], webhook_url: str) -> bool:
    if not records:
        return True
    records = sorted(records, key=lambda r: r.get("score", 0), reverse=True)
    ok = True
    for i in range(0, len(records), MAX_EMBEDS_PER_MESSAGE):
        chunk = records[i : i + MAX_EMBEDS_PER_MESSAGE]
        payload = {"embeds": [format_digest_embed(r) for r in chunk]}
        if i == 0:
            payload["content"] = f"📋 **Daily digest — {len(records)} possible matches (70-84% range)**"
        ok = _post(webhook_url, payload) and ok
    return ok
