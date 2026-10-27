"""Cluster the same story across outlets, then score and select what matters."""
import math
import re
from datetime import datetime, timezone

from . import llm

STOP = set("""a an the of in on at to for and or but with by from as is are was were be been this that
these those it its after before over under into about up down out new says say said maine mainers state
local man woman police county town city amid more than will would could may has have had not no""".split())
OPINION_TAGS = ("opinion", "editorial", "column", "commentary", "letters")


def tokens(title):
    return {w for w in re.findall(r"[a-z0-9']+", title.lower()) if w not in STOP and len(w) > 2}


def _similar(a, b):
    if not a or not b:
        return False
    inter = len(a & b)
    return inter >= 3 and inter / min(len(a), len(b)) >= 0.6 or inter / len(a | b) >= 0.5


def cluster(items):
    clusters = []
    for item in items:
        toks = tokens(item["title"])
        for c in clusters:
            if _similar(toks, c["tokens"]) and not any(i["source"] == item["source"] for i in c["items"]):
                c["items"].append(item)
                c["tokens"] |= toks
                break
        else:
            clusters.append({"items": [item], "tokens": set(toks)})
    for n, c in enumerate(clusters):
        c["id"] = n
        c["items"].sort(key=lambda i: i["published"])  # earliest first: items[0] is the lead outlet
    return clusters


def _heuristic(c, now):
    newest = max(datetime.fromisoformat(i["published"]) for i in c["items"])
    age_h = max((now - newest).total_seconds() / 3600, 0)
    immediacy = math.exp(-age_h / 12)                       # half-life ~8h
    sources = len({i["source"] for i in c["items"]})
    coverage = min(sources, 4) / 4                          # several outlets = big story
    prominence = max(1 / (1 + i["position"] / 5) for i in c["items"])  # near top of a feed
    opinion = any(t.lower().startswith(OPINION_TAGS) for i in c["items"] for t in i["tags"])
    score = 10 * (0.35 * immediacy + 0.4 * coverage + 0.25 * prominence)
    return score * (0.6 if opinion else 1.0)


def _llm_scores(clusters):
    lines = []
    for c in clusters:
        head = c["items"][0]
        outlets = ", ".join(sorted({i["source_short"] for i in c["items"]}))
        lines.append(f'[{c["id"]}] ({outlets}) {head["title"]} :: {head["summary"][:220]}')
    prompt = (
        "You are the news editor of a daily Maine news briefing for one busy Mainer.\n"
        "Only stories with a real Maine angle belong: national or out-of-state stories with no Maine "
        "connection, and generic explainers, score 0-2 on both axes.\n"
        "Score each story from 0-10 on two axes:\n"
        "- importance: statewide or community impact, consequence, breaking/urgent news, public safety, "
        "government, money, health, environment. Routine items, ads, and sports recaps score low.\n"
        "- conversation: how likely it is to spark a good dinner-table or car conversation: surprising, "
        "human, quirky, debatable, distinctly Maine.\n"
        'Return JSON: [{"id": <int>, "importance": <0-10>, "conversation": <0-10>}] for every story.\n\n'
        + "\n".join(lines)
    )
    return {r["id"]: r for r in llm.generate(prompt, json_out=True, temperature=0.2)}


def select(items, count=10, per_source_cap=4, now=None):
    """Return the chosen clusters, best first, each with score components."""
    now = now or datetime.now(timezone.utc)
    clusters = cluster(items)
    for c in clusters:
        c["heuristic"] = _heuristic(c, now)
    clusters.sort(key=lambda c: c["heuristic"], reverse=True)
    pool = clusters[:45]

    scores = {}
    if llm.available():
        try:
            scores = _llm_scores(pool)
        except Exception as exc:
            print(f"LLM scoring failed, using heuristics only: {exc}")
    for c in pool:
        s = scores.get(c["id"], {})
        c["importance"] = float(s.get("importance", c["heuristic"]))
        c["conversation"] = float(s.get("conversation", c["heuristic"] * 0.7))
        c["final"] = 0.4 * c["heuristic"] + 0.35 * c["importance"] + 0.25 * c["conversation"]
    pool.sort(key=lambda c: c["final"], reverse=True)

    chosen, per_source = [], {}
    for c in pool:
        src = c["items"][0]["source"]
        if per_source.get(src, 0) >= per_source_cap:
            continue
        chosen.append(c)
        per_source[src] = per_source.get(src, 0) + 1
        if len(chosen) == count:
            break
    # Guarantee one clear conversation-starter if none made the cut on its own.
    best_talk = max(pool, key=lambda c: c["conversation"])
    if best_talk not in chosen and best_talk["conversation"] >= 6 and chosen:
        chosen[-1] = best_talk
    return chosen
