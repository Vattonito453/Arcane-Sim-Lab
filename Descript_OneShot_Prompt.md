# Descript One-Shot Prompt — "How a distributed team ships in the open"

## Reality check (read once)
Descript builds video from a **script + timeline**, and Underlord (its AI) **can't tell which clip is which from text alone**. So do the 3-minute prep below, then paste the prompt — it handles voiceover, captions, labels, transitions, music, pacing, and export in one pass.

---

## Prep (before pasting — ~3 min)

1. **Rename your 7 exports** so nothing gets mixed up:
   - `V1_Slack-to-Jira`
   - `V2_Huddle-Board`
   - `V3_Board-to-Slack`
   - `V4_Public-Dashboard`
   - `V5_Async-Comments`
   - `V6_Search-History`
   - `V7_Done-Celebrate`
   - *(+ `V0_Map` if your animated opener is ready — optional)*
2. **New Descript project** → drag all clips in.
3. **Order them as scenes** V0→V7 (create a scene per clip, drop the matching clip in). Leave the script text empty — the prompt supplies it.
4. **Paste the prompt below into Underlord.**

---

## The prompt (paste into Underlord)

```
You're editing a ~90-second product demo titled "How a distributed team ships in the open." I've imported clips as ordered scenes named V0_Map (optional) and V1 through V7. Produce a complete first draft in ONE pass. Make reasonable choices and don't ask me questions.

1) VOICEOVER — Generate one AI voiceover for the whole video in a warm, professional, neutral American voice. Use exactly this script, one block per scene, in order:
- V0_Map: "Meet a product team spread across three locations — Memphis, Pittsburgh, Europe."
- V1_Slack-to-Jira: "An idea lands in Slack. One click turns the thread into a Jira ticket — context, comments, and all, so nothing gets lost in translation."
- V2_Huddle-Board: "When something needs a real conversation, a quick huddle pulls in the right people — no meeting invite, no waiting for tomorrow."
- V3_Board-to-Slack: "As work moves through Jira, status updates flow straight into Slack. Design, engineering, and product see the same picture in real time — no handoffs, no status meetings."
- V4_Public-Dashboard: "Everything happens in the open. Stakeholders and business partners can follow along in public channels and live dashboards by default — no status deck required, no waiting on a summary email."
- V5_Async-Comments: "Decisions happen right in the thread, not in someone's inbox. Every comment, every file, every call gets made where the work actually lives."
- V6_Search-History: "Months later, when someone asks 'why did we decide this?' — the answer is one search away. The full history is documented, searchable, and never lost to memory."
- V7_Done-Celebrate: "Synchronous when it matters. Asynchronous by default. Open, documented, and searchable — that's how modern teams flow, without ever needing a handoff."
(If V0_Map isn't present, create a simple title card for that block instead.)

2) SYNC & PACING — Fit each clip to its scene's voiceover length. Trim dead space and hold ~1s at each cut. Keep the full video ~86 seconds. If a clip runs longer than its VO, trim or gently speed-ramp it; if shorter, hold the last frame.

3) CAPTIONS — Add captions from the voiceover: bottom-center, clean bold sans-serif, high contrast with a subtle shadow, animated word-by-word highlight.

4) LABELS / LOWER-THIRDS — On V0_Map add three location labels: "Memphis", "Pittsburgh", "Europe". On V4_Public-Dashboard, label the stakeholder avatar "Partner / Exec".

5) TRANSITIONS — Quick, clean cuts with subtle cross-dissolves between scenes. Give the final scene (V7) a slow pull-back / zoom-out feel to close.

6) MUSIC — Add an upbeat but understated corporate/tech background track. Duck it under the voiceover (~20% volume). Fade in at the start, fade out at the end.

7) POLISH — Remove filler and dead air, apply Studio Sound / noise reduction to the voiceover, and apply smart transitions where they help.

8) OUTPUT — Target 1080p, 60fps, 16:9. When finished, give me a short summary of what you changed and flag anything that looks off.
```

---

## If you'd rather use your own voice
Swap step 1: instead of generating AI VO, paste each scene's line into that scene's script and record your voice on it. Keep steps 2–8 as-is.

## Quick fixes if the draft is off
- **Wrong clip on a scene** → drag the correct clip from the media bin onto that scene.
- **VO too fast/slow** → adjust the AI voice speed, or re-time the scene.
- **Captions look wrong** → Captions panel in the sidebar to restyle.
- **Music too loud** → click the music track → Volume ~20%.

## Export
Publish → **1080p** (or up to 4K), **60fps**, MP4/H.264.
```
