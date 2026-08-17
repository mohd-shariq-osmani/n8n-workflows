#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import urllib.parse
import re
from datetime import datetime, timezone, timedelta

def generate_digest():
    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        env_file = os.path.join(os.path.dirname(__file__), ".env")
        if os.path.exists(env_file):
            with open(env_file) as f:
                for line in f:
                    if line.startswith("DISCORD_BOT_TOKEN="):
                        token = line.split("=", 1)[1].strip().strip('"\'')
                        break

    channels = [
        {"id": "1527849679683850250", "name": "Recipes", "channelTag": "#recipe", "icon": "🍳"},
        {"id": "1527858846985486366", "name": "Tech & Projects", "channelTag": "#projects", "icon": "💻"},
        {"id": "1527858942594646056", "name": "Workouts", "channelTag": "#workout", "icon": "🏋️"},
        {"id": "1538893352668233789", "name": "Anime & Manhwa", "channelTag": "#anime-manhua", "icon": "🎌"},
        {"id": "1527859066259374212", "name": "Movies & TV", "channelTag": "#movie-tv", "icon": "🎬"},
        {"id": "1538704806900797450", "name": "General & Articles", "channelTag": "#others", "icon": "📌"}
    ]

    now_utc = datetime.now(timezone.utc)
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = now_utc.astimezone(ist_tz)
    date_str = now_ist.strftime("%B %d, %Y")
    one_day_ago = now_utc - timedelta(hours=24)

    categorized_items = []
    total_count = 0

    for c in channels:
        try:
            url = f"https://discord.com/api/v10/channels/{c['id']}/messages?limit=25"
            req = urllib.request.Request(url, headers={
                "Authorization": f"Bot {token}",
                "User-Agent": "DiscordBot (https://discord.com, 1.0)"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                msgs = json.loads(resp.read().decode("utf-8"))

            valid_items = []
            if isinstance(msgs, list):
                for m in msgs:
                    ts_str = m.get("timestamp", "")
                    if ts_str:
                        ts_clean = ts_str.replace("Z", "+00:00")
                        msg_time = datetime.fromisoformat(ts_clean)
                        if msg_time < one_day_ago:
                            continue

                    author = m.get("author", {})
                    if not author.get("bot"):
                        continue

                    content = m.get("content", "")
                    if not content or any(p in content for p in ["*(Part 2/", "*(Part 3/", "*(Part 4/"]):
                        continue

                    # Extract title from markdown header
                    title_match = re.search(r'^#\s+[🍳💻🏋️🎌🎬📌🎭]?\s*([^\n]+)', content, re.MULTILINE)
                    if not title_match:
                        title_match = re.search(r'^\*\*([^\n]+)\*\*', content, re.MULTILINE)

                    title = title_match.group(1).strip() if title_match else ""
                    title = re.sub(r'[#*`>]', '', title).strip()

                    if not title or len(title) < 3 or any(title.startswith(b) for b in ["Where to Watch", "Bonus Note", "Links:", "Update:"]):
                        continue

                    # Extract link
                    gh_match = re.search(r'🔗?\s*\*\*GitHub:\*\*\s*(https?://\S+)', content, re.IGNORECASE)
                    imdb_match = re.search(r'🎬?\s*\*\*IMDb:\*\*\s*(https?://\S+)', content, re.IGNORECASE)
                    src_match = re.search(r'🔗?\s*\*\*Source:\*\*\s*(https?://\S+)', content, re.IGNORECASE) or re.search(r'https?://\S+', content)

                    link = ""
                    if gh_match:
                        link = gh_match.group(1).strip()
                    elif imdb_match:
                        link = imdb_match.group(1).strip()
                    elif src_match:
                        link = src_match.group(1).strip()

                    msg_id = m.get("id")
                    channel_id = m.get("channel_id")
                    message_link = f"https://discord.com/channels/{channel_id}/{msg_id}"
                    final_link = link or message_link

                    if not any(v["title"].lower() == title.lower() for v in valid_items):
                        valid_items.append({"title": title, "link": final_link})
                        total_count += 1

            if valid_items:
                categorized_items.append({
                    "name": c["name"],
                    "channelTag": c["channelTag"],
                    "icon": c["icon"],
                    "items": valid_items
                })
        except Exception:
            continue

    if categorized_items:
        markdown = f"# 🗞️ Daily Digest — {date_str}\n> ⏱️ *Daily recap of {total_count} {'item' if total_count == 1 else 'items'} curated across channels in the last 24 hours.*\n\n"
        for cat in categorized_items:
            markdown += f"### {cat['icon']} {cat['name']} (`{cat['channelTag']}`)\n"
            for it in cat['items']:
                markdown += f"• [{it['title']}]({it['link']})\n"
            markdown += "\n"
        markdown += "---\n*⚡ Next daily digest tomorrow at 11:00 PM IST.*"
    else:
        markdown = f"# 🗞️ Daily Digest — {date_str}\n> ⏱️ *No new items were posted across channels in the last 24 hours. Send links or images to curate content!*"

    print(json.dumps({
        "digestMarkdown": markdown,
        "totalCount": total_count,
        "date": date_str
    }))

if __name__ == "__main__":
    generate_digest()
