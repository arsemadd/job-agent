"""Discord notifier.

Uses an incoming webhook (POST a JSON payload, no persistent bot connection
needed for one-way notifications, per the brief). Message shapes:

  - send_immediate(): one full-detail message per SEND-tier job
  - send_digest(): batched embeds for DIGEST-tier jobs
  - send_run_summary(): short run heartbeat so quiet days still surface activity
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger("job_agent.discord")

DISCORD_CONTENT_LIMIT = 2000
MAX_EMBEDS_PER_MESSAGE = 5
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
    why = ", ".join((record.get("why_matches") or [])[:2]) or "see link"
    gaps = ", ".join((record.get("gaps") or [])[:2]) or "none noted"
    # Discord total embed payload limit is 6000 chars — keep each card tiny.
    why = why[:140] + ("…" if len(why) > 140 else "")
    gaps = gaps[:100] + ("…" if len(gaps) > 100 else "")
    title = f"{_score_emoji(score)} {score}% — {record.get('title', '')}"
    title = title[:250] + ("…" if len(title) > 250 else "")
    company = (record.get("company") or "Unknown")[:80]
    location = (record.get("location_raw") or "Remote")[:80]
    description = f"**{company}** · {location}\n**Why:** {why}\n**Gaps:** {gaps}"
    if len(description) > 400:
        description = description[:397] + "…"
    return {
        "title": title,
        "url": record.get("url") or None,
        "description": description,
        "color": 0x2F6FED if score >= 80 else 0x5B8FF0,
    }


def format_run_summary(summary: dict) -> str:
    immediate = int(summary.get("sent_immediate") or 0)
    digest = int(summary.get("digest_sent") or 0)
    scored = int(summary.get("scored") or 0)
    new = int(summary.get("new_postings") or 0)
    passed = int(summary.get("passed_hard_filters") or 0)
    total = int(summary.get("total_in_store") or 0)
    alerts = immediate + digest
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    if alerts:
        headline = f"✅ **Job Matcher** ({now}) — {alerts} alert(s) sent"
    else:
        headline = (
            f"ℹ️ **Job Matcher** ({now}) — ran successfully, "
            f"but **no jobs scored high enough** for Discord "
            f"(need ≥65 digest / ≥85 immediate)"
        )
    return (
        f"{headline}\n"
        f"New postings: **{new}** · Passed filters: **{passed}** · Scored: **{scored}**\n"
        f"Immediate: **{immediate}** · Digest: **{digest}** · Store: **{total}** roles"
    )


def _forum_enabled() -> bool:
    """Forum thread fields only when explicitly enabled.

    Always attaching thread_name creates a new Discord thread per message, which
    hides alerts from the main channel view. Opt in with DISCORD_FORUM=1 or by
    setting DISCORD_THREAD_ID / DISCORD_THREAD_NAME.
    """
    flag = (os.environ.get("DISCORD_FORUM") or "").strip().lower()
    if flag in {"1", "true", "yes", "forum"}:
        return True
    if (os.environ.get("DISCORD_THREAD_ID") or "").strip():
        return True
    if (os.environ.get("DISCORD_THREAD_NAME") or "").strip():
        return True
    return False


def _forum_fields(thread_name: str | None = None, force: bool = False) -> dict:
    if not force and not _forum_enabled():
        return {}
    thread_id = os.environ.get("DISCORD_THREAD_ID", "").strip()
    if thread_id:
        return {"thread_id": thread_id}
    name = (thread_name or os.environ.get("DISCORD_THREAD_NAME") or "Job Matcher").strip()
    return {"thread_name": name[:100]}


def _post(webhook_url: str, payload: dict, max_retries: int = 3, thread_name: str | None = None) -> bool:
    """Post to Discord. Auto-retries with forum thread fields on error 220001."""
    url = webhook_url if "wait=" in webhook_url else (
        webhook_url + ("&" if "?" in webhook_url else "?") + "wait=true"
    )
    use_forum = _forum_enabled()
    for attempt in range(1, max_retries + 1):
        body = {**payload, **_forum_fields(thread_name, force=use_forum)}
        try:
            resp = requests.post(url, json=body, timeout=15)
            if resp.status_code == 429:
                retry_after = float(resp.json().get("retry_after", 1))
                time.sleep(retry_after + 0.5)
                continue
            if resp.status_code >= 400:
                err_text = (resp.text or "")[:400]
                # Forum webhooks require thread_name/thread_id — opt in and retry.
                if resp.status_code == 400 and "220001" in err_text and not use_forum:
                    logger.info("discord webhook is a forum channel — retrying with thread_name")
                    use_forum = True
                    continue
                logger.warning(
                    "discord post failed (attempt %d/%d): HTTP %s %s",
                    attempt,
                    max_retries,
                    resp.status_code,
                    err_text[:300],
                )
                time.sleep(1.5 * attempt)
                continue
            return True
        except requests.RequestException as exc:
            logger.warning("discord post failed (attempt %d/%d): %s", attempt, max_retries, exc)
            time.sleep(1.5 * attempt)
    return False


def send_immediate(record: dict, webhook_url: str) -> bool:
    content = format_immediate_message(record)
    score = int(record.get("score") or 0)
    title = (record.get("title") or "Match")[:60]
    thread_name = f"{score}% — {title}"
    return _post(webhook_url, {"content": content}, thread_name=thread_name)


def send_digest(records: list[dict], webhook_url: str) -> bool:
    if not records:
        return True
    records = sorted(records, key=lambda r: r.get("score", 0), reverse=True)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ok = True
    for i in range(0, len(records), MAX_EMBEDS_PER_MESSAGE):
        chunk = records[i : i + MAX_EMBEDS_PER_MESSAGE]
        payload = {"embeds": [format_digest_embed(r) for r in chunk]}
        if i == 0:
            payload["content"] = f"📋 **Digest — {len(records)} possible matches (65–84% range)**"
        thread_name = f"Digest {day}" if i == 0 else f"Digest {day} ({i // MAX_EMBEDS_PER_MESSAGE + 1})"
        chunk_ok = _post(webhook_url, payload, thread_name=thread_name)
        if not chunk_ok and len(chunk) > 1:
            # Fall back to one embed per message if the batch is still too large.
            logger.info("discord digest batch failed — retrying %d embeds one-by-one", len(chunk))
            for j, record in enumerate(chunk):
                single = {"embeds": [format_digest_embed(record)]}
                if i == 0 and j == 0:
                    single["content"] = payload.get("content")
                single_ok = _post(
                    webhook_url,
                    single,
                    thread_name=f"{thread_name} · {j + 1}",
                )
                chunk_ok = single_ok and chunk_ok if j else single_ok
        ok = chunk_ok and ok
        time.sleep(0.7)
    return ok


def send_run_summary(summary: dict, webhook_url: str) -> bool:
    """Post a short heartbeat so quiet runs are still visible in-channel."""
    content = format_run_summary(summary)
    return _post(webhook_url, {"content": content}, thread_name="Job Matcher runs")
