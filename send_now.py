from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from backend.notifications import discord

store_path = Path("data/jobs.json")
data = json.loads(store_path.read_text(encoding="utf-8"))
pending = [j for j in data["jobs"] if j.get("status") == "digest_pending"]
webhook = os.environ["DISCORD_WEBHOOK_URL"]
print("pending", len(pending), flush=True)
for j in pending:
    print(j.get("score"), j.get("title"), j.get("company"), flush=True)
ok = discord.send_digest(pending, webhook) if pending else True
print("sent", ok, flush=True)
if ok and pending:
    now = datetime.now(timezone.utc).isoformat()
    for job in pending:
        job["status"] = "digest_sent"
        job["notified_at"] = now
    tmp = store_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, store_path)
    print("store updated", flush=True)
