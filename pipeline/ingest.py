"""Fetch and normalize items from every outlet's RSS feeds."""
import calendar
import hashlib
import html
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests
import yaml

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 RegardingMaine/1.0")
SOURCES_PATH = Path(__file__).parent / "sources.yaml"


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def load_config():
    return yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8"))


def _entry_time(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    return None


def fetch_feed(url):
    last = None
    attempts = (  # some CDNs stall on particular header sets, so vary them
        {"User-Agent": "Mozilla/5.0", "Accept": "application/rss+xml,application/xml,text/xml,*/*"},
        {},
        {"User-Agent": UA},
    )
    for headers in attempts:
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            return feedparser.parse(resp.content)
        except requests.RequestException as exc:
            last = exc
            if getattr(exc.response, "status_code", None) == 429:
                time.sleep(6)  # polite backoff, then try the next header set
    raise last


def ingest(max_age_hours=48, config=None):
    """Return (items, report). Items are newest-first dicts; failures are non-fatal."""
    config = config or load_config()
    exclude = re.compile("|".join(config.get("exclude_patterns", [])) or r"(?!x)", re.I)
    now = datetime.now(timezone.utc)
    items, seen, report = [], set(), {}

    for src in config["sources"]:
        count = 0
        for url in src["feeds"]:
            try:
                feed = fetch_feed(url)
            except Exception as exc:  # one broken feed must not sink the edition
                report.setdefault(src["id"], []).append(f"FAIL {url}: {exc}")
                continue
            for pos, entry in enumerate(feed.entries):
                link = entry.get("link", "").split("#")[0]
                title = clean(entry.get("title"))
                if not link or not title or link in seen:
                    continue
                tags = [clean(t.get("term", "")) for t in entry.get("tags", [])]
                if exclude.search(title) or any(exclude.search(t) for t in tags):
                    continue
                published = _entry_time(entry) or now
                if (now - published).total_seconds() > max_age_hours * 3600:
                    continue
                seen.add(link)
                summary = clean(entry.get("summary") or entry.get("description"))
                items.append({
                    "id": hashlib.sha1(link.encode()).hexdigest()[:12],
                    "source": src["id"],
                    "source_name": src["name"],
                    "source_short": src["short"],
                    "source_spoken": src.get("spoken", src["name"]),
                    "title": title,
                    "url": link,
                    "published": published.isoformat(),
                    "summary": summary[:600],
                    "content": clean("".join(c.get("value", "") for c in entry.get("content", [])))[:6000],
                    "tags": tags,
                    "position": pos,
                })
                count += 1
        report.setdefault(src["id"], []).insert(0, f"{count} items")
    items.sort(key=lambda i: i["published"], reverse=True)
    return items, report


if __name__ == "__main__":
    found, rep = ingest()
    for sid, lines in rep.items():
        print(sid, lines)
    print(len(found), "total")
