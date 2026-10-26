"""Maintain the static site: editions.json, episode MP3s, and the podcast RSS feed."""
import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "site"
KEEP_DAYS = int(os.environ.get("RM_KEEP_DAYS", "10"))
TITLE = "Regarding Maine"
TAGLINE = "The Maine news worth knowing, twice a day."


def site_dir():
    slug = os.environ.get("RM_SLUG", "").strip("/")
    return ROOT / "dist" / slug if slug else ROOT / "dist"


def base_url():
    return os.environ.get("RM_BASE_URL", "").rstrip("/")


def _load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def restore_state(out):
    """Pages deploys replace the whole site, so pull recent editions back from the live copy."""
    base = base_url()
    if not base:
        return
    try:
        resp = requests.get(f"{base}/data/editions.json", timeout=30)
        resp.raise_for_status()
        editions = resp.json()
    except Exception as exc:
        print(f"No previous state restored ({exc})")
        return
    (out / "data").mkdir(parents=True, exist_ok=True)
    (out / "data" / "editions.json").write_text(json.dumps(editions), encoding="utf-8")
    for ed in editions:
        audio = ed.get("audio")
        target = out / "episodes" / f"{ed['id']}.mp3"
        if audio and not target.exists():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                r = requests.get(f"{base}/episodes/{ed['id']}.mp3", timeout=120)
                r.raise_for_status()
                target.write_bytes(r.content)
            except Exception as exc:
                print(f"Could not restore {ed['id']} audio: {exc}")
                ed["audio"] = None
    (out / "data" / "editions.json").write_text(json.dumps(editions), encoding="utf-8")


def add_edition(out, edition):
    path = out / "data" / "editions.json"
    editions = [e for e in _load(path) if e["id"] != edition["id"]]
    editions.insert(0, edition)
    cutoff = datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS)
    kept = [e for e in editions if datetime.fromisoformat(e["published"]) >= cutoff]
    for e in editions:
        if e not in kept:
            (out / "episodes" / f"{e['id']}.mp3").unlink(missing_ok=True)
    kept.sort(key=lambda e: e["published"], reverse=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(kept, indent=1), encoding="utf-8")
    return kept


def write_feed(out, editions):
    base = base_url()
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd", "atom": "http://www.w3.org/2005/Atom"}
    for prefix, uri in ns.items():
        ET.register_namespace(prefix, uri)
    rss = ET.Element("rss", version="2.0")
    ch = ET.SubElement(rss, "channel")
    for tag, text in (("title", TITLE), ("link", f"{base}/"), ("language", "en-us"),
                      ("description", TAGLINE), ("lastBuildDate", format_datetime(datetime.now(timezone.utc)))):
        ET.SubElement(ch, tag).text = text
    ET.SubElement(ch, f"{{{ns['itunes']}}}author").text = TITLE
    ET.SubElement(ch, f"{{{ns['itunes']}}}explicit").text = "false"
    ET.SubElement(ch, f"{{{ns['itunes']}}}block").text = "Yes"  # keep it out of public directories
    ET.SubElement(ch, f"{{{ns['itunes']}}}image", href=f"{base}/cover.png")
    ET.SubElement(ch, f"{{{ns['itunes']}}}category", text="News")
    ET.SubElement(ch, f"{{{ns['atom']}}}link", href=f"{base}/feed.xml", rel="self",
                  type="application/rss+xml")
    for ed in editions:
        if not ed.get("audio"):
            continue
        item = ET.SubElement(ch, "item")
        ET.SubElement(item, "title").text = ed["title"]
        ET.SubElement(item, "description").text = "\n".join(
            f"- {s['headline']}" for s in ed["stories"])
        ET.SubElement(item, "guid", isPermaLink="false").text = ed["id"]
        ET.SubElement(item, "pubDate").text = format_datetime(datetime.fromisoformat(ed["published"]))
        ET.SubElement(item, "enclosure", url=f"{base}/episodes/{ed['id']}.mp3",
                      length=str(ed["audio"]["bytes"]), type="audio/mpeg")
        ET.SubElement(item, f"{{{ns['itunes']}}}duration").text = str(ed["audio"]["seconds"])
    ET.indent(rss)
    ET.ElementTree(rss).write(out / "feed.xml", encoding="utf-8", xml_declaration=True)


def copy_static(out):
    out.mkdir(parents=True, exist_ok=True)
    for f in STATIC.iterdir():
        if f.is_file():
            shutil.copy2(f, out / f.name)
