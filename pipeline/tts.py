"""Narrate the script with Microsoft Edge neural voices (free) into one MP3."""
import asyncio
import os
import re
import tempfile
from pathlib import Path

import edge_tts
from mutagen.mp3 import MP3

VOICE = os.environ.get("RM_VOICE", "en-US-AndrewNeural")
RATE = os.environ.get("RM_RATE", "+0%")
CHUNK_CHARS = 2800


def _chunks(script):
    paras = [p.strip() for p in re.split(r"\n\s*\n", script) if p.strip()]
    chunk = ""
    for p in paras:
        if chunk and len(chunk) + len(p) > CHUNK_CHARS:
            yield chunk
            chunk = ""
        chunk += ("\n\n" if chunk else "") + p
    if chunk:
        yield chunk


async def _synth(text, path):
    for attempt in range(4):
        try:
            await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(path))
            return
        except Exception:
            if attempt == 3:
                raise
            await asyncio.sleep(3 * (attempt + 1))


def narrate(script, out_path):
    """Write an MP3 to out_path; returns duration in seconds."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async def run(tmp):
        parts = []
        for n, text in enumerate(_chunks(script)):
            part = Path(tmp) / f"part{n:03d}.mp3"
            await _synth(text, part)
            parts.append(part)
        return parts

    with tempfile.TemporaryDirectory() as tmp:
        parts = asyncio.run(run(tmp))
        with open(out_path, "wb") as out:  # same encoder settings, so MP3 frames concatenate cleanly
            for part in parts:
                out.write(part.read_bytes())
    return int(MP3(out_path).info.length)
