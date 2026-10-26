# Regarding Maine

Twice-daily Maine news digest (web app) and podcast (private RSS feed), built from six Maine outlets.

## Run locally
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
set GEMINI_API_KEY=...        (optional; without it, ranking is heuristic and the script is a template)
set RM_BASE_URL=http://localhost:8000
python -m pipeline.run --edition auto        (add --no-audio to skip narration)
python -m http.server 8000 --directory dist
```

## Deploy (GitHub Pages, free)
1. Push this folder to a **public** GitHub repo (Pages needs public on the free plan).
2. Settings → Pages → Source: **GitHub Actions**.
3. Settings → Secrets → Actions: add `GEMINI_API_KEY` (free key from aistudio.google.com) and
   `RM_SLUG` (a long random string; it becomes the private path of your app and feed).
4. Run the "Regarding Maine edition" workflow manually once. Your app is at
   `https://<user>.github.io/<repo>/<RM_SLUG>/` and the podcast feed at `.../feed.xml`.

## Tuning
- Outlets and feeds: `pipeline/sources.yaml`
- Ranking weights, selection size: `pipeline/rank.py`
- Voice: set `RM_VOICE` (default `en-US-AndrewNeural`)
