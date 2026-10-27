"""Turn selected story clusters into a text digest and a podcast script.

Attribution is assembled in code, never left to the model: the lead outlet of a cluster is the one that
published first (a proxy for the original reporting), and the spoken line "According to <outlet>," always
comes before the story.
"""
import re

from . import llm


def _first_sentences(text, n=2, limit=280):
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out = " ".join(parts[:n])
    return out if len(out) <= limit else out[: limit - 1].rstrip() + "…"


def _lead(c):
    return c["items"][0]  # rank.cluster orders items earliest-published first


def _story_input(c):
    return {
        "id": c["id"],
        "reported_by": _lead(c)["source_name"],
        "headlines": [i["title"] for i in c["items"]],
        "text": [i.get("text") or i["summary"] for i in c["items"][:2] if i.get("text") or i["summary"]],
    }


def _links(c):
    return [{"outlet": i["source_short"], "title": i["title"], "url": i["url"]} for i in c["items"]]


def _json_by_id(prompt):
    return {r["id"]: r for r in llm.generate(prompt, json_out=True, temperature=0.3)}


def build_digest(clusters):
    """Return a list of story dicts: headline, summary, why, talk, outlets, links."""
    written = {}
    if llm.available():
        try:
            written = _json_by_id(
                "Write a brief news digest for a Maine news briefing called 'Regarding Maine'.\n"
                "For each story below write, in your OWN words (never copy sentences from the article text; "
                "get names, places and numbers exactly right):\n"
                '- "headline": a plain, punchy headline under 12 words\n'
                '- "summary": 2 sentences, 45 words max, factual, no hype, based only on the material given\n'
                '- "why": one short sentence on why a Mainer might care (or empty string)\n'
                '- "talk": for stories that make a good conversation-starter, a one-sentence question to '
                "chew on; otherwise an empty string\n"
                'Return JSON: [{"id": <int>, "headline": "", "summary": "", "why": "", "talk": ""}]\n\n'
                f"STORIES:\n{[_story_input(c) for c in clusters]}"
            )
        except Exception as exc:
            print(f"LLM digest failed, using extractive fallback: {exc}")

    stories = []
    for c in clusters:
        lead = _lead(c)
        w = written.get(c["id"], {})
        outlets = [lead["source_short"]] + sorted({i["source_short"] for i in c["items"]} - {lead["source_short"]})
        stories.append({
            "id": c["id"],
            "headline": w.get("headline") or lead["title"],
            "summary": w.get("summary") or _first_sentences(lead["summary"]) or "",
            "why": w.get("why", ""),
            "talk": w.get("talk", ""),
            "outlets": outlets,
            "attribution": lead["source_spoken"],
            "links": _links(c),
            "score": round(c["final"], 2),
        })
    return stories


def _cap(name):
    return name[0].upper() + name[1:]


def build_script(stories, clusters, label, date_text):
    """Spoken script: a one-line opener, then each story led by its attribution. No banter."""
    by_id = {c["id"]: c for c in clusters}
    bodies = {}
    if llm.available():
        try:
            inputs = []
            for s in stories:
                item = _story_input(by_id[s["id"]])
                item["outlet_spoken"] = s["attribution"]
                inputs.append(item)
            bodies = _json_by_id(
                "You write the spoken text of a Maine news audio briefing. For each story write a 'body': "
                "the news itself, told plainly in 3-6 sentences (70-150 words; give the biggest stories "
                "more room). Rules:\n"
                "- The body is read right AFTER the words 'According to <outlet_spoken>,' so begin it as the "
                "continuation of that sentence (for example 'the city council voted...'). Do not name the "
                "outlet yourself and do not mention any other outlet.\n"
                "- Lead with what happened, then the key facts: who, what, where, numbers, what happens next.\n"
                "- No greetings, no opinions, no commentary, no rhetorical questions, no filler, no "
                "transitions between stories, no phrases like 'meanwhile' or 'in other news'.\n"
                "- Use only facts in the provided text; never quote it verbatim. Write numbers and "
                "names so they read aloud naturally.\n"
                'Return JSON: [{"id": <int>, "body": ""}]\n\n'
                f"STORIES:\n{inputs}"
            )
        except Exception as exc:
            print(f"LLM script failed, using template: {exc}")

    paragraphs = [f"Regarding Maine, {label.lower()} edition, {date_text}."]
    for s in stories:
        body = (bodies.get(s["id"], {}).get("body") or "").strip()
        if body:
            paragraphs.append(f"According to {s['attribution']}, {body}")
        else:  # template fallback keeps attribution first even without the model
            paragraphs.append(f"{_cap(s['attribution'])} reports. {s['headline']}. {s['summary']}")
    paragraphs.append("That's Regarding Maine.")
    return "\n\n".join(paragraphs)
