"""Turn selected story clusters into a text digest and a podcast script."""
import re

from . import llm


def _first_sentences(text, n=2, limit=280):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out = " ".join(parts[:n])
    return out if len(out) <= limit else out[: limit - 1].rstrip() + "…"


def _story_input(c):
    head = c["items"][0]
    return {
        "id": c["id"],
        "outlets": sorted({i["source_name"] for i in c["items"]}),
        "headlines": [i["title"] for i in c["items"]],
        "excerpts": [i["summary"] for i in c["items"] if i["summary"]][:3],
    }


def _links(c):
    return [{"outlet": i["source_short"], "title": i["title"], "url": i["url"]} for i in c["items"]]


def build_digest(clusters):
    """Return a list of story dicts: headline, summary, why, talk, outlets, links."""
    written = {}
    if llm.available():
        try:
            prompt = (
                "Write a brief news digest for a Maine news briefing called 'Regarding Maine'.\n"
                "For each story below write, in your OWN words (never copy sentences from the excerpts):\n"
                '- "headline": a plain, punchy headline under 12 words\n'
                '- "summary": 2 sentences, 45 words max, factual, no hype, based only on the material given\n'
                '- "why": one short sentence on why a Mainer might care (or empty string)\n'
                '- "talk": for stories that make a good conversation-starter, a one-sentence question to '
                "chew on; otherwise an empty string\n"
                'Return JSON: [{"id": <int>, "headline": "", "summary": "", "why": "", "talk": ""}]\n\n'
                f"STORIES:\n{[_story_input(c) for c in clusters]}"
            )
            written = {r["id"]: r for r in llm.generate(prompt, json_out=True, temperature=0.3)}
        except Exception as exc:
            print(f"LLM digest failed, using extractive fallback: {exc}")

    stories = []
    for c in clusters:
        head = c["items"][0]
        w = written.get(c["id"], {})
        stories.append({
            "id": c["id"],
            "headline": w.get("headline") or head["title"],
            "summary": w.get("summary") or _first_sentences(head["summary"]) or "",
            "why": w.get("why", ""),
            "talk": w.get("talk", ""),
            "outlets": sorted({i["source_short"] for i in c["items"]}),
            "links": _links(c),
            "score": round(c["final"], 2),
        })
    return stories


def build_script(stories, label, date_text):
    """Spoken script, ~8-12 minutes (1,200-1,800 words) when an LLM is available."""
    if llm.available():
        try:
            prompt = (
                "Write the spoken script for 'Regarding Maine', a Maine news podcast with ONE warm, "
                f"conversational host. This is the {label.lower()} edition for {date_text}.\n"
                "Rules: 1,700-2,000 words (the last draft ran short). Plain spoken English, no markdown, no stage directions, no "
                "bullet lists. Open with a short greeting and a one-line preview. Cover every story in "
                "order of the list, giving the most important ones more time. Credit the outlet aloud "
                "('according to the Press Herald'). Never quote articles verbatim. Near the end add a "
                "short 'Worth talking about' segment built from the talk questions. Close with a quick "
                "sign-off and a reminder that links to every story are in the app.\n\n"
                f"STORIES:\n{stories}"
            )
            return llm.generate(prompt, temperature=0.6)
        except Exception as exc:
            print(f"LLM script failed, using template: {exc}")

    lines = [f"Welcome to Regarding Maine. This is your {label.lower()} briefing for {date_text}.", ""]
    for n, s in enumerate(stories, 1):
        who = " and ".join(s["outlets"][:2])
        lines.append(f"Story {n}. {s['headline']}. {s['summary']} That's reporting from {who}.")
        lines.append("")
    talks = [s for s in stories if s["talk"]]
    if talks:
        lines.append("Worth talking about. " + " ".join(s["talk"] for s in talks[:2]))
        lines.append("")
    lines.append("That's your briefing. Links to every story are in the Regarding Maine app. Take care out there.")
    return "\n".join(lines)
