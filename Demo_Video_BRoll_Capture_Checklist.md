# Demo Video — B-Roll Capture Checklist

**Project:** Slack / Jira / Airtable demo — "how a distributed FedEx Digital team works"
**Team story:** one product idea travels Memphis → Pittsburgh → Europe and ships, all in the open.
**Total runtime:** ~1:26 · **To record:** 7 live screen-capture vignettes · **To animate:** 2 world-map bookends

---

## How to use this

Do **Part A once** (build the demo environment and stage all content). Then work through **Part B**, recording one vignette at a time — each has a *Setup*, an *On-screen action*, and *Recording notes*. Parts C–E cover the animated bookends, the smartest order to shoot in, and light edit notes. Check off boxes as you go.

> **Golden rule for continuity:** every vignette follows the **same ticket** through its life. Stage that one ticket (see Part A) so it looks consistent in every shot.

---

## Part A — One-time setup (do this before recording anything)

### A1. Demo environment

- [ ] **Slack:** a clean workspace (or a dedicated demo channel) — public channel `#proj-tracking-eta`
- [ ] **Jira:** a demo project (e.g. key `TRACK`) with a board using columns **To Do → In Progress → Review → Done**
- [ ] **Airtable:** a base for the initiative + one **Interface page** to act as the "live dashboard" (status / roadmap view)
- [ ] **Integrations (for scenes 2 & 4):** install the **Jira Cloud app for Slack** so you can (a) turn a message into an issue and (b) post board updates into the channel. *If you can't wire it live, fake it — post the bot-style messages by hand and cut them together in edit.*

### A2. The story spine (the one ticket that runs through everything)

| Element | Value (placeholder — swap for your real demo data) |
|---|---|
| Initiative / Epic | **Delivery ETA on the Tracking Page** |
| Slack idea (scene 2) | *"What if the tracking page showed a live delivery window?"* |
| Jira ticket | **TRACK-482 — Show live delivery window on tracking page** |
| The decision (scene 6/7) | *"Use the carrier ETA feed for v1; revisit an ML estimate later."* |
| Ships (scene 8) | TRACK-482 → **Done** |

### A3. Cast & avatars (consistent across Slack, Jira, Airtable)

| Name | Role | Location | Handle |
|---|---|---|---|
| Dana Reyes | Product Manager | Memphis | `@dana` |
| Marcus Lee | Engineer | Pittsburgh | `@marcus` |
| Sofia Kovač | Designer | Europe | `@sofia` |
| Priya Nair | Business Partner / Exec (the "follower") | Memphis | `@priya` |

- [ ] Set a **real profile photo** for each so avatars read clearly on screen
- [ ] Use the **same names/photos** in Jira assignees, Slack messages, and Airtable owner fields

### A4. Content to pre-load

- [ ] **Slack thread** in `#proj-tracking-eta`: Dana's idea message + 2–3 emoji reactions + a short reply or two
- [ ] **Jira ticket TRACK-482** with title, description, assignee, and the board card visible
- [ ] **Comment thread on TRACK-482** (for scene 6): 5–8 comments from Dana/Marcus/Sofia with timestamps spread across different hours (shows async)
- [ ] **Airtable dashboard** showing TRACK-482's status/progress so it looks "live"
- [ ] **Priya added** as a member of the public channel and a viewer of the dashboard (the quiet "follower")

### A5. Recording tech

- [ ] Tool that gives you **cursor + zoom control** (ScreenFlow, OBS, or macOS `Cmd+Shift+5`)
- [ ] Record at **native res, export 1920×1080; 60 fps** (smoother for UI motion)
- [ ] **Dedicated browser profile:** no personal bookmarks, extensions, or tabs; hide the bookmarks bar
- [ ] **Do Not Disturb / Focus on;** quit mail, calendar, and other Slack workspaces (kill notification pop-ups)
- [ ] Turn on **cursor highlight / click visualization;** move slowly and deliberately
- [ ] Pick **one zoom level** (browser ~125–150%) and keep it across shots so cuts match
- [ ] Hide personal info in the menu bar / clock; neutral wallpaper
- [ ] For every take: **hold still ~1.5s at the start and end** (gives clean trim handles), and record **2–3× the target length** so you can trim to the voiceover

---

## Part B — The 7 vignettes to record

### Vignette 1 — Idea in Slack becomes a Jira ticket
*Scene 2 · 0:08–0:18 · target ~10s · Slack (→ Jira)*
> **Narration:** "An idea lands in Slack. One click turns the thread into a Jira ticket — context, comments, and all, so nothing gets lost in translation."

- [ ] **Setup:** `#proj-tracking-eta` open on Dana's idea message with a couple of reactions/replies already on it
- [ ] **Action:** hover the message → open the **`...` actions menu** → click **"Create Jira issue"** → the dialog fills → confirm → the **linked ticket card** (TRACK-482) appears back in the thread
- [ ] **Recording:** two clean takes — one on the menu/click, one on the linked card appearing. Emphasize the *one-click* moment.

### Vignette 2 — Quick huddle with the Jira board shared
*Scene 3 · 0:18–0:28 · target ~10s · Slack huddle + Jira*
> **Narration:** "When something needs a real conversation, a quick huddle pulls in the right people — no meeting invite, no waiting for tomorrow."

- [ ] **Setup:** channel open; be ready to start a **Slack huddle;** have the Jira board in another window/tab to screen-share
- [ ] **Action:** click the **huddle** control → it pulses/starts → two avatars (Marcus, Sofia) join → **share screen** showing the Jira board mid-conversation
- [ ] **Recording:** capture the huddle starting and the avatars joining; then a beat of the shared board. Fine to shoot the join and the share as two clips and cut together.

### Vignette 3 — Card moves across the board and posts to Slack
*Scene 4 · 0:28–0:40 · target ~12s · Jira (→ Slack)*
> **Narration:** "As work moves through Jira, status updates flow straight into Slack. Design, engineering, and product see the same picture in real time — no handoffs, no status meetings."

- [ ] **Setup:** Jira board visible with TRACK-482 in an early column; channel ready in a second window for the auto-post
- [ ] **Action:** **drag TRACK-482** across a column (e.g. In Progress → Review) → cut to Slack where the **status-update message** posts into the channel
- [ ] **Recording:** drag slowly and land the card cleanly. If the live Slack post isn't wired up, record the drag and a manually-posted update separately, then cut them back-to-back.

### Vignette 4 — Everything in the open: public channel + live dashboard
*Scene 5 · 0:40–0:52 · target ~12s · Slack + Airtable*
> **Narration:** "Everything happens in the open. Stakeholders and business partners can follow along in public channels and live dashboards by default — no status deck required, no waiting on a summary email."

- [ ] **Setup:** show the **public** channel (Priya visible in the member list, labeled Partner/Exec); have the **Airtable dashboard** ready in a second tab
- [ ] **Action:** pan/scroll the public channel → switch to the **Airtable interface dashboard** showing TRACK-482's live status → linger so it reads as "no private DMs, no separate deck"
- [ ] **Recording:** get a clean shot of the member list (the quiet follower), then the dashboard. Make the dashboard look current and tidy.

### Vignette 5 — Async decision-making in the ticket comments
*Scene 6 · 0:52–1:04 · target ~12s · Jira*
> **Narration:** "Decisions happen right in the thread, not in someone's inbox. Every comment, every file, every call gets made where the work actually lives."

- [ ] **Setup:** open **TRACK-482's comment thread** with the pre-loaded comments (different avatars, timestamps across different hours)
- [ ] **Action:** **scroll the comment thread** so replies fill in; optionally type a fresh comment and hit send; show a file attachment on one comment
- [ ] **Recording:** smooth, steady scroll. Make sure timestamps are legible — they sell the "async, across time zones" point.

### Vignette 6 — "Why did we decide this?" — search surfaces the history
*Scene 7 · 1:04–1:16 · target ~12s · Slack search + Jira search*
> **Narration:** "Months later, when someone asks 'why did we decide this?' — the answer is one search away. The full history is documented, searchable, and never lost to memory."

- [ ] **Setup:** clear search boxes ready in both Slack and Jira; know exactly which thread and which comment you'll surface
- [ ] **Action:** **type "why did we decide this?"** into search → results surface the **exact Slack thread**; then a quick second shot of Jira/issue search surfacing **TRACK-482** and the decision comment
- [ ] **Recording:** type at a readable pace (or speed up in post). Capture the thread result and the ticket result as two micro-shots to cut between.

### Vignette 7 — It ships: card to Done + Slack celebration
*Scene 8 · 1:16–1:26 · target ~10s · Jira + Slack (→ animated pull-back)*
> **Narration:** "Synchronous when it matters. Asynchronous by default. Open, documented, and searchable — that's how modern teams flow, without ever needing a handoff."

- [ ] **Setup:** TRACK-482 sitting just before **Done;** channel ready for reactions
- [ ] **Action:** **drag the card into "Done"** → cut to Slack where the channel **lights up with celebratory emoji reactions** (🎉✅🚀) → hold for the animated camera pull-back (Part C)
- [ ] **Recording:** land the card in Done cleanly; stack a few emoji reactions quickly so the channel visibly "lights up." Leave a clean tail for the pull-back transition.

---

## Part C — Animated bookends (not recorded — brief for your motion designer)

### Bookend 1 — Opening world map
*Scene 1 · 0:00–0:08 · ~8s*
> **Narration:** "Meet a product team spread across three locations — Memphis, Pittsburgh, Europe."

- [ ] World map, **glowing pins on Memphis, Pittsburgh, Europe** connecting into a single network
- [ ] Establish the three-location look and the color palette used in the UI shots

### Bookend 2 — Closing pull-back
*Tail of Scene 8 · ~1:16–1:26*

- [ ] Camera **pulls back from the Slack celebration to the full connected network** from Bookend 1 (visual callback that closes the loop)
- [ ] Match the pins/colors to the opening so it reads as the same network

---

## Part D — Smartest capture-day order

Pre-stage all content first, then shoot in this order so the **ticket visibly progresses toward Done** and nothing contradicts a later shot:

1. **V1** — create TRACK-482 from Slack *(ticket now exists)*
2. **V2** — huddle + share board *(card in an early column)*
3. **V3** — drag card across the board *(advance it)*
4. **V5** — comment thread scroll *(comments already staged)*
5. **V4** — public channel + Airtable dashboard *(reflects current progress)*
6. **V7** — card to Done + celebration *(final state)*
7. **V6** — search "why did we decide this?" *(shoot last — all history now exists to surface)*

**Only hard rule:** the Jira card should look like it's moving forward across V1 → V3 → V7. Everything else can be shot in any order.

---

## Part E — Post / edit notes

- [ ] Drop clips onto the timeline in scene order; **trim each to its target duration** and sync to the voiceover
- [ ] Use consistent transitions (quick cross-dissolve or match-cut) between Slack ↔ Jira ↔ Airtable
- [ ] Add **captions/labels** where helpful ("Memphis", "Pittsburgh", "Europe", "Partner", "Exec")
- [ ] Layer the **VO + light music bed;** keep UI clicks subtle or silent
- [ ] Export **1920×1080, 60 fps, H.264;** check text is legible at final size

---

### Coverage check

7 recorded vignettes (scenes 2–8) + 2 animated bookends (scene 1 + scene 8 tail) = all 8 storyboard beats, ~1:26 total. Placeholder names/ticket are fully swappable — replace with your real demo accounts before shooting.
