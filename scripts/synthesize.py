#!/usr/bin/env python3
"""
Render an episode script to MP3.

Engines
-------
piper      free, offline neural voices. No API key. Voice names look like
           "en_GB-alba-medium". Models are fetched from HuggingFace on first use
           and cached in .voice-cache/.
elevenlabs paid. Needs ELEVENLABS_API_KEY. Voice is a voice id.
google     paid. Needs GOOGLE_TTS_API_KEY. Voice looks like "en-GB-Chirp3-HD-Puck".
azure      paid. Needs AZURE_TTS_KEY and AZURE_TTS_REGION. Voice looks like
           "en-GB-RyanNeural".

Usage
-----
  python scripts/synthesize.py --engine piper --voice en_GB-alba-medium \
      --text episodes/2026-10-06.md --out audio/2026-10-06.mp3

The script file may carry a YAML front matter block; it is stripped before
synthesis. Lines beginning with "#" are treated as headings and spoken without
the hashes. Anything inside [[...]] is treated as a production note and dropped.

Every episode opens with the sting in assets/, unless --no-jingle is passed or
the file is absent.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

CACHE = Path(".voice-cache")

# Long scripts have to be cut up: the hosted APIs cap a single request at a few
# thousand characters, and piper is happier with paragraph-sized chunks too.
CHUNK_LIMIT = 2200

# The opening sting, and the silence between it and the first spoken word.
JINGLE = Path("assets/2026-10-07_behsci-brief-jingle.wav")
JINGLE_GAP = 0.4


# --------------------------------------------------------------------------- #
# Script preparation
# --------------------------------------------------------------------------- #

def load_script(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")

    # Strip YAML front matter.
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            raw = parts[2]

    # Drop production notes.
    raw = re.sub(r"\[\[.*?\]\]", "", raw, flags=re.DOTALL)

    lines = []
    for line in raw.splitlines():
        line = line.rstrip()
        if line.startswith("#"):
            line = line.lstrip("#").strip()
            # A heading needs a beat after it.
            lines.append(line + ".")
            continue
        lines.append(line)

    text = "\n".join(lines)

    # Markdown emphasis would otherwise be read out as asterisks.
    text = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", text)
    text = re.sub(r"_{1,2}([^_]+)_{1,2}", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Collapse runs of blank lines to a single paragraph break.
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def chunk(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """Split on paragraph boundaries, never mid-sentence."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    out: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > limit:
            # Oversized paragraph: fall back to sentence boundaries.
            sentences = re.split(r"(?<=[.!?])\s+", para)
            for sentence in sentences:
                if len(current) + len(sentence) + 1 > limit and current:
                    out.append(current.strip())
                    current = ""
                current += sentence + " "
            continue
        if len(current) + len(para) + 2 > limit and current:
            out.append(current.strip())
            current = ""
        current += para + "\n\n"
    if current.strip():
        out.append(current.strip())
    return out


# --------------------------------------------------------------------------- #
# Engines. Each returns a list of WAV or MP3 file paths, in order.
# --------------------------------------------------------------------------- #

def synth_piper(chunks: list[str], voice: str, workdir: Path) -> list[Path]:
    import importlib

    CACHE.mkdir(parents=True, exist_ok=True)
    model = CACHE / f"{voice}.onnx"
    if not model.exists():
        subprocess.run(
            [sys.executable, "-m", "piper.download_voices", voice,
             "--data-dir", str(CACHE)],
            check=True,
        )

    piper = importlib.import_module("piper")
    voice_obj = piper.PiperVoice.load(str(model))

    import wave

    paths = []
    for i, text in enumerate(chunks):
        out = workdir / f"part{i:04d}.wav"
        with wave.open(str(out), "wb") as wav:
            voice_obj.synthesize_wav(text, wav)
        paths.append(out)
    return paths


def _post_json(url: str, payload: dict, headers: dict) -> bytes:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:600]
        raise SystemExit(f"{url} returned {exc.code}: {body}") from exc


def synth_elevenlabs(chunks: list[str], voice: str, workdir: Path) -> list[Path]:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set.")
    model = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
    headers = {"xi-api-key": key, "Content-Type": "application/json",
               "Accept": "audio/mpeg"}
    paths = []
    for i, text in enumerate(chunks):
        audio = _post_json(url, {
            "text": text,
            "model_id": model,
            "voice_settings": {"stability": 0.45, "similarity_boost": 0.75,
                               "style": 0.0, "use_speaker_boost": True},
        }, headers)
        out = workdir / f"part{i:04d}.mp3"
        out.write_bytes(audio)
        paths.append(out)
    return paths


def synth_google(chunks: list[str], voice: str, workdir: Path) -> list[Path]:
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        raise SystemExit("GOOGLE_TTS_API_KEY is not set.")
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}"
    language = "-".join(voice.split("-")[:2])
    paths = []
    for i, text in enumerate(chunks):
        body = _post_json(url, {
            "input": {"text": text},
            "voice": {"languageCode": language, "name": voice},
            "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.96},
        }, {"Content-Type": "application/json"})
        out = workdir / f"part{i:04d}.mp3"
        out.write_bytes(base64.b64decode(json.loads(body)["audioContent"]))
        paths.append(out)
    return paths


def synth_azure(chunks: list[str], voice: str, workdir: Path) -> list[Path]:
    key = os.environ.get("AZURE_TTS_KEY")
    region = os.environ.get("AZURE_TTS_REGION")
    if not (key and region):
        raise SystemExit("AZURE_TTS_KEY and AZURE_TTS_REGION must both be set.")
    url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
    language = "-".join(voice.split("-")[:2])
    paths = []
    for i, text in enumerate(chunks):
        ssml = (
            f'<speak version="1.0" xml:lang="{language}">'
            f'<voice name="{voice}"><prosody rate="-4%">'
            f"{_xml_escape(text)}</prosody></voice></speak>"
        )
        req = urllib.request.Request(
            url, data=ssml.encode("utf-8"), method="POST",
            headers={
                "Ocp-Apim-Subscription-Key": key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
                "User-Agent": "behavioural-science-brief",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                audio = resp.read()
        except urllib.error.HTTPError as exc:
            raise SystemExit(
                f"Azure returned {exc.code}: "
                f"{exc.read().decode('utf-8', 'replace')[:600]}"
            ) from exc
        out = workdir / f"part{i:04d}.mp3"
        out.write_bytes(audio)
        paths.append(out)
    return paths


def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


ENGINES = {
    "piper": synth_piper,
    "elevenlabs": synth_elevenlabs,
    "google": synth_google,
    "azure": synth_azure,
}


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def concatenate(parts: list[Path], out: Path, title: str, date: str,
                jingle: Path | None = None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as listing:
        for part in parts:
            listing.write(f"file '{part.resolve()}'\n")
        listing_path = listing.name

    # A short pause between chunks reads as a paragraph break rather than a cut.
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", listing_path,
    ]

    if jingle is not None:
        # The sting is already mastered to -16 LUFS, so only the speech goes
        # through loudnorm; putting music through the same dynamic pass as
        # speech makes the transition pump. The two are then joined with the
        # concat FILTER rather than the demuxer, because the demuxer insists on
        # identical codec parameters and the engines above emit a mixture of
        # 22.05 kHz WAV and 24 kHz MP3.
        cmd += ["-i", str(jingle)]
        cmd += [
            "-filter_complex",
            (
                "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11,"
                "aresample=44100,aformat=sample_fmts=s16:channel_layouts=mono"
                "[speech];"
                "[1:a]aresample=44100,aformat=sample_fmts=s16:channel_layouts=mono,"
                f"apad=pad_dur={JINGLE_GAP}[sting];"
                "[sting][speech]concat=n=2:v=0:a=1[out]"
            ),
            "-map", "[out]",
        ]
    else:
        cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]

    cmd += [
        "-codec:a", "libmp3lame", "-b:a", "96k", "-ar", "44100", "-ac", "1",
        "-metadata", f"title={title}",
        "-metadata", "artist=Behavioural Science Daily Brief",
        "-metadata", "album=Behavioural Science Daily Brief",
        "-metadata", f"date={date}",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    os.unlink(listing_path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True, choices=sorted(ENGINES))
    ap.add_argument("--voice", required=True)
    ap.add_argument("--text", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--title", default="")
    ap.add_argument("--jingle", type=Path, default=JINGLE,
                    help="Opening sting prepended to the episode.")
    ap.add_argument("--no-jingle", action="store_true",
                    help="Render speech only.")
    args = ap.parse_args()

    jingle = None
    if not args.no_jingle:
        if args.jingle and args.jingle.exists():
            jingle = args.jingle
        else:
            print(f"note: {args.jingle} not found, rendering without the "
                  f"opening sting", flush=True)

    text = load_script(args.text)
    if not text:
        raise SystemExit(f"{args.text} produced no speakable text.")
    chunks = chunk(text)
    date = args.text.stem

    print(f"{args.engine}/{args.voice}: {len(text)} characters "
          f"in {len(chunks)} chunk(s)", flush=True)

    with tempfile.TemporaryDirectory() as tmp:
        parts = ENGINES[args.engine](chunks, args.voice, Path(tmp))
        concatenate(parts, args.out, args.title or date, date, jingle)

    size = args.out.stat().st_size
    print(f"wrote {args.out} ({size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
