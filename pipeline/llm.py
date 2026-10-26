"""Thin Gemini (free tier) client. Everything downstream works without a key."""
import json
import os
import time

import requests

MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"


def available():
    return bool(os.environ.get("GEMINI_API_KEY"))


def generate(prompt, json_out=False, temperature=0.4):
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature}}
    if json_out:
        body["generationConfig"]["responseMimeType"] = "application/json"
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
    for attempt in range(5):
        resp = requests.post(URL.format(MODEL), headers=headers, json=body, timeout=180)
        if resp.status_code in (429, 500, 503):
            time.sleep(8 * (attempt + 1))  # free tier rate limits are per-minute
            continue
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text) if json_out else text.strip()
    raise RuntimeError("Gemini unavailable after retries")
