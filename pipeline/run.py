"""Build one edition: python -m pipeline.run [--edition morning|evening|auto] [--no-audio]"""
import argparse
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from . import digest, fulltext, ingest, publish, rank

ET = ZoneInfo("America/New_York")


def pick_edition(now_et, requested):
    if requested != "auto":
        return requested
    return "morning" if now_et.hour < 14 else "evening"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", default="auto", choices=["auto", "morning", "evening"])
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--count", type=int, default=10)
    args = ap.parse_args()

    now_et = datetime.now(ET)
    edition = pick_edition(now_et, args.edition)
    label = edition.capitalize()
    date_text = f"{now_et:%A, %B} {now_et.day}"
    # Morning looks back a full day; evening covers roughly since the morning edition.
    max_age = 30 if edition == "morning" else 14

    items, report = ingest.ingest(max_age_hours=max_age)
    for sid, lines in report.items():
        print(f"  {sid}: {'; '.join(lines)}")
    if len(items) < 5:
        sys.exit("Too few items fetched; refusing to publish a thin edition.")

    chosen = rank.select(items, count=args.count)
    fulltext.enrich(chosen)
    stories = digest.build_digest(chosen)
    script = digest.build_script(stories, label, date_text)

    out = publish.site_dir()
    publish.restore_state(out)
    publish.copy_static(out)

    ed_id = f"{now_et:%Y-%m-%d}-{edition}"
    record = {
        "id": ed_id,
        "label": label,
        "title": f"Regarding Maine: {label}, {date_text}",
        "date_text": date_text,
        "published": datetime.now(timezone.utc).isoformat(),
        "stories": stories,
        "script": script,
        "audio": None,
    }
    if not args.no_audio:
        from . import tts
        mp3 = out / "episodes" / f"{ed_id}.mp3"
        seconds = tts.narrate(script, mp3)
        record["audio"] = {"seconds": seconds, "bytes": mp3.stat().st_size}
        print(f"Audio: {seconds // 60}m{seconds % 60:02d}s, {mp3.stat().st_size / 1e6:.1f} MB")

    editions = publish.add_edition(out, record)
    publish.write_feed(out, editions)
    print(f"Published {ed_id} with {len(stories)} stories to {out}")


if __name__ == "__main__":
    main()
