#!/usr/bin/env python3
"""
Rebuild feed.xml from whatever is in audio/ and episodes/.

One episode per MP3 in audio/, named YYYY-MM-DD.mp3. The matching
episodes/YYYY-MM-DD.md supplies the title and summary, taken from its YAML
front matter if present and inferred otherwise. Durations come from ffprobe,
byte lengths from the file itself; Apple Podcasts is fussy about both.

Usage
-----
  python scripts/build_feed.py --base-url https://user.github.io/repo
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

SHOW = {
    "title": "Behavioural Science Daily Brief",
    "subtitle": "New research in behavioural science, psychology and behavioural economics",
    "author": "Jean-Marc Debricon",
    "owner_name": "Jean-Marc Debricon",
    "owner_email": "jmdebricon@mac.com",
    "language": "en-GB",
    "category": "Science",
    "subcategory": "Social Sciences",
    "description": (
        "A daily reading of new working papers, peer-reviewed articles and "
        "policy work in behavioural science, psychology and behavioural "
        "economics, prepared for a first-year undergraduate on the LSE BSc "
        "Psychological and Behavioural Science. Each episode gives the "
        "finding, the method, the sample and the limitations, with a concept "
        "of the day and a note on research methods."
    ),
}


def duration_seconds(path: Path) -> int:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", str(path)],
        capture_output=True, text=True, check=True,
    )
    return int(float(json.loads(out.stdout)["format"]["duration"]))


def hhmmss(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def front_matter(path: Path) -> tuple[dict, str]:
    if not path.exists():
        return {}, ""
    raw = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            for line in parts[1].strip().splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    meta[key.strip()] = value.strip().strip('"').strip("'")
            body = parts[2]
    return meta, body.strip()


def summary_from_body(body: str, limit: int = 600) -> str:
    body = re.sub(r"\[\[.*?\]\]", "", body, flags=re.DOTALL)
    paragraphs = [
        p.strip() for p in body.split("\n\n")
        if p.strip() and not p.strip().startswith("#")
    ]
    if not paragraphs:
        return SHOW["subtitle"]
    text = " ".join(paragraphs[:2])
    text = re.sub(r"\s+", " ", text)
    return text[:limit].rsplit(" ", 1)[0] + ("..." if len(text) > limit else "")


def build(base_url: str, root: Path) -> str:
    base_url = base_url.rstrip("/")
    audio_dir = root / "audio"
    episode_dir = root / "episodes"

    items = []
    files = sorted(audio_dir.glob("*.mp3"), reverse=True) if audio_dir.exists() else []

    for mp3 in files:
        stem = mp3.stem
        try:
            day = datetime.strptime(stem, "%Y-%m-%d").replace(
                hour=6, minute=30, tzinfo=timezone.utc)
        except ValueError:
            print(f"skipping {mp3.name}: filename is not YYYY-MM-DD.mp3")
            continue

        meta, body = front_matter(episode_dir / f"{stem}.md")
        title = meta.get("title") or f"{day:%A %-d %B %Y}"
        summary = meta.get("summary") or summary_from_body(body)
        seconds = duration_seconds(mp3)

        items.append(f"""    <item>
      <title>{escape(title)}</title>
      <description>{escape(summary)}</description>
      <itunes:summary>{escape(summary)}</itunes:summary>
      <pubDate>{format_datetime(day)}</pubDate>
      <guid isPermaLink="false">behsci-brief-{stem}</guid>
      <enclosure url="{base_url}/audio/{mp3.name}" length="{mp3.stat().st_size}" type="audio/mpeg"/>
      <itunes:duration>{hhmmss(seconds)}</itunes:duration>
      <itunes:episodeType>full</itunes:episodeType>
      <itunes:explicit>false</itunes:explicit>
    </item>""")

    now = format_datetime(datetime.now(timezone.utc))
    body = "\n".join(items)

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(SHOW['title'])}</title>
    <link>{base_url}/</link>
    <atom:link href="{base_url}/feed.xml" rel="self" type="application/rss+xml"/>
    <language>{SHOW['language']}</language>
    <description>{escape(SHOW['description'])}</description>
    <itunes:summary>{escape(SHOW['description'])}</itunes:summary>
    <itunes:subtitle>{escape(SHOW['subtitle'])}</itunes:subtitle>
    <itunes:author>{escape(SHOW['author'])}</itunes:author>
    <itunes:owner>
      <itunes:name>{escape(SHOW['owner_name'])}</itunes:name>
      <itunes:email>{escape(SHOW['owner_email'])}</itunes:email>
    </itunes:owner>
    <itunes:image href="{base_url}/assets/cover.jpg"/>
    <itunes:category text="{SHOW['category']}">
      <itunes:category text="{SHOW['subcategory']}"/>
    </itunes:category>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <itunes:block>Yes</itunes:block>
    <lastBuildDate>{now}</lastBuildDate>
    <pubDate>{now}</pubDate>
{body}
  </channel>
</rss>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True,
                    help="e.g. https://username.github.io/repo-name")
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    xml = build(args.base_url, args.root)
    out = args.out or (args.root / "feed.xml")
    out.write_text(xml, encoding="utf-8")
    count = xml.count("<item>")
    print(f"wrote {out} with {count} episode(s)")


if __name__ == "__main__":
    main()
