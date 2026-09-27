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

`tools/make_dck.py` resolves every name with `engine/forge_index.py`'s
`ForgeIndex.resolve()`, built from `~/forge/res/cardsfolder/cardsfolder.zip`
(Forge 2.0.13): the same normalisation as `engine/convert_decklist.py`.
Transform, modal, battle, adventure and flip cards become the front face;
true split cards keep "A // B".

**Corrected 2026-09-27 (repair plan WS4 task 6).** This section used to say
DFCs resolved to the front face. They did not: the old resolver matched
script file names, every DFC has a `front_back.txt` script like a split card,
so "Front // Back" was written unchanged and Forge refused it on stderr. 48
slots in 23 of the 32 decks were played without the card, both Ral commanders
included. Its prefix match also accepted `_____ Goblin`, which Forge does not
have. All 32 decks were regenerated; the only changes are the 48 front-face
renames and the `_____ Goblin` substitute below, and a Forge load check of
all 8 pods now reports 0 refused cards (it reported those 50 before).

Recorded substitutions (all in `manifest.json` notes, here, and in
`make_dck.py` `RECORDED_SUBSTITUTES`, so a regeneration needs no flags):

| Published card | Not in Forge 2.0.13 | Substitute | Deck | Why |
|---|---|---|---|---|
| Dragon-Cursed Halls | land | Mountain | magda | plain land slot |
| Fíli and Kíli, Joyous | dwarf creature | Seven Dwarves | magda, natalie_magda | keeps Dwarf count for Magda |
| Dwarven Mauler | dwarf creature | Dwarven Warriors | magda, natalie_magda | keeps Dwarf count |
| Óin the Brave | dwarf creature | Dwarven Pony | magda, natalie_magda | keeps Dwarf count |
| Gleaming Splendor | land | Island | dallas_bluefarm | plain land slot |
| _____ Goblin | sticker creature ({2}{R}, ETB adds {R} per unique vowel on its sticker) | Priest of Urabrask | joseph_ral (both pods) | same slot: a three-mana creature that adds {R}{R}{R} on entering. Added 2026-09-27; before that Forge silently dropped the card |

Regenerate every deck: `py studies/human_ceiling/tools/make_dck.py
studies/human_ceiling/decks/*/*.txt --in-place`.

## Copyright posture

Transcripts and video metadata are creator content held for private analysis
only, same regime as `rules/raw/`: strip `data/transcripts/` and `data/meta/`
before the repo ever goes public. `traces/*.json` are our own structured
extraction and can stay.
