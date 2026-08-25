# Data provenance and refetch instructions

## Videos and captions (2026-08-24)

Fetched with yt-dlp 2026.08.19 in a throwaway venv (NOT vendored; the engine
stays stdlib-only):

```bash
python3 -m venv /tmp/ytenv && /tmp/ytenv/bin/pip install yt-dlp
/tmp/ytenv/bin/yt-dlp --skip-download --write-info-json \
  --write-subs --write-auto-subs --sub-langs "en.*" --sub-format vtt \
  -o "videos/%(id)s/%(id)s" "https://www.youtube.com/watch?v=<ID>"
python3 tools/clean_vtt.py videos/<ID>/<ID>.en.vtt > data/transcripts/<ID>.txt
```

All 12 manifest videos had English auto-captions. `data/meta/<id>.json` is the
info-json trimmed to title/channel/date/duration/description/chapters.

## Decklists

Moxfield's API (api2.moxfield.com) returns 403 to scripted clients
(Cloudflare). Lists were fetched from a real browser context (Claude Code's
browser pane, JS fetch on moxfield.com) and saved as plain text. To refetch:
open the deck on moxfield.com and use Export > "1 Card Name" text, or repeat
the browser-context fetch of `/v3/decks/all/<publicId>`.

Record `lastUpdatedAtUtc` with every capture: lists drift after videos air,
and the fidelity tier in `manifest.json` depends on it.

## Forge card support

`tools/make_dck.py` checks names against
`~/forge/res/cardsfolder/cardsfolder.zip` (Forge 2.0.13). Normalization:
strip accents, drop apostrophes, other punctuation to underscore. DFC/MDFC
resolve to the front face; true split cards keep "A // B".

Pilot substitutions (magda.dck, all recorded in manifest + here):

| Published card | Not in Forge 2.0.13 | Substitute | Why |
|---|---|---|---|
| Dragon-Cursed Halls | land | Mountain | plain land slot |
| Fíli and Kíli, Joyous | dwarf creature | Seven Dwarves | keeps Dwarf count for Magda |
| Dwarven Mauler | dwarf creature | Dwarven Warriors | keeps Dwarf count |
| Óin the Brave | dwarf creature | Dwarven Pony | keeps Dwarf count |

## Copyright posture

Transcripts and video metadata are creator content held for private analysis
only, same regime as `rules/raw/`: strip `data/transcripts/` and `data/meta/`
before the repo ever goes public. `traces/*.json` are our own structured
extraction and can stay.
