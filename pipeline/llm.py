"""Thin Gemini (free tier) client. Everything downstream works without a key."""
import json
import os
import time

import requests

# Google retires models often (2.5 Flash now 404s for new keys), so try a chain of current ones.
MODELS = ([os.environ["GEMINI_MODEL"]] if os.environ.get("GEMINI_MODEL") else []) + [
    "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite"]
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
_working = []  # model that last succeeded, tried first on later calls


def available():
    return bool(os.environ.get("GEMINI_API_KEY"))


def generate(prompt, json_out=False, temperature=0.4):
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature}}
    if json_out:
        body["generationConfig"]["responseMimeType"] = "application/json"
    headers = {"x-goog-api-key": os.environ["GEMINI_API_KEY"]}
    errors = []
    for model in _working + [m for m in MODELS if m not in _working]:
        for attempt in range(3):
            resp = requests.post(URL.format(model), headers=headers, json=body, timeout=180)
            if resp.status_code in (429, 500, 503):
                time.sleep(10 * (attempt + 1))  # free tier rate limits are per-minute
                continue
            break
        if resp.status_code != 200:
            errors.append(f"{model}: {resp.status_code} {resp.text[:160]}")
            continue
        try:
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            result = json.loads(text) if json_out else text.strip()
        except (KeyError, IndexError, ValueError) as exc:
            errors.append(f"{model}: bad response ({exc})")
            continue
        _working[:] = [model]
        print(f"Gemini model in use: {model}")
        return result
    raise RuntimeError("Gemini failed: " + " | ".join(errors))
