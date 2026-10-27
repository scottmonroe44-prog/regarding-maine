"""Fetch article text for the stories that made the cut, so summaries rest on more than an RSS stub.

The text is used only as input for summarizing; it is never published. Press Herald and BDN serve most
article text without a login (their paywalls are metered in the browser). If you are a subscriber you can
still pass your browser's cookie header as RM_COOKIE_PPH / RM_COOKIE_BDN to get past a hard block.
"""
import os
import re
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup

from .ingest import UA

MAX_CHARS = 3500
MIN_CHARS = 500  # shorter than this means a paywall stub or an extraction miss
JUNK = re.compile(
    r"sign into your|subscribe|log in|cookie|newsletter|all rights reserved|advertisement|"
    r"^Δ|©|read more:|related:|click here|follow us on|download our app|premium content|"
    r"proud to make|more by |our (political|journalists|communities)", re.I)
CUTOFF = re.compile(r"please sign into your|join the conversation|comments? (are|have been)|^Δ", re.I)
COOKIES = {"pph": "RM_COOKIE_PPH", "bdn": "RM_COOKIE_BDN"}


def extract(html_text):
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "figure"]):
        tag.decompose()
    root = (soup.find(class_=re.compile(r"entry-content|article-body|story-body|post-content|c-article"))
            or soup.find("article") or soup.body or soup)
    out = []
    for p in root.find_all("p"):
        text = re.sub(r"\s+", " ", p.get_text(" ", strip=True))
        if CUTOFF.search(text):
            break
        if len(text) >= 60 and not JUNK.search(text):
            out.append(text)
    return " ".join(out)


def _fetch(item):
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "text/html,application/xhtml+xml,*/*"}
    cookie = os.environ.get(COOKIES.get(item["source"], ""), "")
    if cookie:
        headers["Cookie"] = cookie
    base = {k: v for k, v in headers.items() if k == "Cookie"}
    # Some CDNs (NEWS CENTER) stall on browser-like headers, so also try a bare request.
    for attempt in (dict(headers), dict(base), {**base, "User-Agent": UA}):
        try:
            resp = requests.get(item["url"], headers=attempt, timeout=20)
            resp.raise_for_status()
            text = extract(resp.text)
            if len(text) >= MIN_CHARS:
                return text[:MAX_CHARS]
        except requests.RequestException:
            continue
    return ""


def enrich(clusters, per_cluster=2):
    """Attach item['text'] to the lead items of each cluster; falls back to feed content."""
    items = [i for c in clusters for i in c["items"][:per_cluster]]

    def work(item):
        feed_text = item.get("content", "")
        item["text"] = feed_text[:MAX_CHARS] if len(feed_text) >= MIN_CHARS else _fetch(item)
        return bool(item["text"])

    with ThreadPoolExecutor(max_workers=6) as pool:
        got = sum(pool.map(work, items))
    print(f"Article text for {got} of {len(items)} items")
