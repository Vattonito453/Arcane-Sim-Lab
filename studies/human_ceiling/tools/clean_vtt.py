#!/usr/bin/env python3
"""Clean YouTube auto-caption .vtt files into timestamped transcripts.

YouTube auto-captions repeat each line as a rolling window (the same text
appears in consecutive cues as it scrolls). This collapses the roll into one
line per utterance and keeps a [mm:ss] stamp so extracted plays can be
checked against the video.

Usage:
  python3 clean_vtt.py input.en.vtt > transcript.txt
"""
from __future__ import annotations

import re
import sys

TS = re.compile(r"^(\d+):(\d+):(\d+)\.(\d+)\s+-->")
TAG = re.compile(r"<[^>]+>")


def clean(path: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    last_text = None
    cur_secs = 0
    for raw in open(path, encoding="utf-8"):
        raw = raw.strip()
        if not raw or raw.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        m = TS.match(raw)
        if m:
            h, mnt, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            cur_secs = h * 3600 + mnt * 60 + s
            continue
        text = TAG.sub("", raw).replace("&gt;", ">").replace("&lt;", "<")
        text = text.replace("&amp;", "&").strip()
        if not text or text == last_text:
            continue
        # rolling-window repeat: the new cue starts with the tail of the last
        if last_text and text.startswith(last_text):
            text_new = text[len(last_text):].strip()
            if text_new:
                out.append((cur_secs, text_new))
                last_text = text
            continue
        out.append((cur_secs, text))
        last_text = text
    return out


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    for secs, text in clean(sys.argv[1]):
        print(f"[{secs // 60:02d}:{secs % 60:02d}] {text}")


if __name__ == "__main__":
    main()
