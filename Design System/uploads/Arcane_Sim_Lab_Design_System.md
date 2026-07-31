# 🧙‍♂️ Arcane Sim Lab — Design System & UI Specification

Welcome to the official Design System specification for **Arcane Sim Lab** (formerly *Magic Sim Lab*), an automated playtesting, goldfish simulation, and matchup analytics platform for *Magic: The Gathering* (specifically Commander/EDH).

This document outlines the visual language, typography, color palette, component specs, and UI guidelines developed for the platform's home screen and dashboard interface.

---

## 📄 Table of Contents
1. [Brand Identity & Core Concept](#1-brand-identity--core-concept)
2. [Color Palette & Tokens](#2-color-palette--tokens)
3. [Typography Hierarchy](#3-typography-hierarchy)
4. [Component Specifications](#4-component-specifications)
5. [Layout & Structural Grid](#5-layout--structural-grid)
6. [IP Protection & Compliance](#6-ip-protection--compliance)
7. [Monetization Integration](#7-monetization-integration)

---

## 1. 🛡️ Brand Identity & Core Concept

### 1.1 Thematic Vision: "Arcane Automation"
* **Environment:** Set against a backdrop reminiscent of **Dominaria** — featuring ancient floating hedron monoliths, moss-covered stone ruins, and ambient blue-violet mana leyline currents flowing through the sky.
* **Mascot / Logo Logo:** **The Arcane Automation** — A cheerful, magical brass-and-bronze robot artifact creature sitting atop the header. It glows with arcane energy and holds a hand of MTG cards, signaling a playful, welcoming approach to deep mathematical deck testing.
* **Tone:** Equal parts **high fantasy** (evoking classical MTG lore) and **scientific precision** (emphasizing powerful automated goldfish and matchup simulation engines).

---

## 2. 🎨 Color Palette & Tokens

The UI utilizes a dark-mode base paired with high-contrast glowing accents to maintain readability over rich environmental artwork while preserving the feel of the five MTG colors ($WUBRG$).

### 2.1 Base & Surface Colors
| Token Name | Hex Code | Visual Use / Description |
| :--- | :--- | :--- |
| `--bg-void` | `#0D0F12` | Deep space background base behind artwork. |
| `--surface-obsidian` | `#161B22` | Card backgrounds, search inputs, and dark panels. |
| `--surface-glass-dark` | `rgba(15, 20, 28, 0.85)` | Frosted glass panel backdrop for data readability. |
| `--surface-glass-border`| `rgba(56, 189, 248, 0.25)` | Subtle glowing border for main content panels. |

### 2.2 Accent & Glow Effects
| Token Name | Hex Code | Visual Use / Description |
| :--- | :--- | :--- |
| `--mana-cyan` | `#00E5FF` | Primary CTA glowing borders, data pulses, active states. |
| `--arcane-violet` | `#A855F7` | Secondary accents, spell energy, interactive highlights. |
| `--glow-cyan-cyan` | `0 0 15px rgba(0, 229, 255, 0.5)` | Box-shadow glow for the "Run New Simulation" button. |

### 2.3 Color Identity System ($WUBRG$ Accents)
To avoid trademark issues while retaining MTG identity, abstract geometric color dots and glowing badges are used:

| Mana Color | Token Name | Hex Code | Visual Badge Icon |
| :--- | :--- | :--- | :--- |
| **White ($W$)** | `--color-sun` | `#F59E0B` | ☀️ Warm Gold Sun Dot |
| **Blue ($U$)** | `--color-water` | `#00E5FF` | 💧 Mana Cyan Water Drop Dot |
| **Black ($B$)** | `--color-skull` | `#A855F7` | 💀 Arcane Purple Skull Dot |
| **Red ($R$)** | `--color-fire` | `#EF4444` | 🔥 Flame Red Flame Dot |
| **Green ($G$)** | `--color-tree` | `#10B981` | 🌲 Emerald Forest Tree Dot |

### 2.4 Card Rarity Accents (UI States)
* **Common:** Silver-Gray (`#94A3B8`)
* **Uncommon:** Teal-Cyan (`#2DD4BF`)
* **Rare:** Warm Gold (`#F59E0B`)
* **Mythic:** Copper Flame / Neon Orange (`#F97316`)

---

## 3. 🔤 Typography Hierarchy

The typographic system pairs high-fantasy serif headings with clean, modern monospaced and sans-serif fonts for data precision.

| Role | Font Family | Size / Weight | Application |
| :--- | :--- | :--- | :--- |
| **Primary Logo Title** | Serif (e.g., *Cinzel*, *Trajan*) | `28pt / Bold / Uppercase` | `ARCANE SIM LAB` Main Title |
| **Section Headers** | Serif / Semi-Bold | `16pt - 18pt / Semi-Bold` | Section Headings (`Top decklists`, `Most recent sims`) |
| **CTA Buttons** | Geometric Sans / Bold | `12pt - 14pt / Bold / All-Caps` | Action Buttons (`RUN NEW SIMULATION`) |
| **Data & Statistics** | Monospace (e.g., *JetBrains Mono*) | `11pt - 13pt / Regular` | Rolling Tallies, Percentages, Timestamps |
| **Body / Meta Text** | Clean Sans-Serif | `10pt - 11pt / Regular` | Deck Names, Subtitles, Rules Engine Footer |

---

## 4. 🧩 Component Specifications

### 4.1 Header & Mascot Section
* **Mascot Placement:** Centered top header logo featuring the "Arcane Automation" robot sitting above the main title.
* **Account Widget:** Positioned top-right (`VD Account ˅`), formatted as a translucent pill button with a user avatar icon.

### 4.2 The Rolling Tally Banner
* **Container:** Dark metallic instrument bar (`#111827`) with rounded corners and subtle border stroke.
* **Live Counters:**
  * ☀️ `52,365 decks tested`
  * 💧 `343,621 games simulated`
  * 💀 `32,013 commanders used`
  * 🔷 `1,121 infinite combos detected`
* **Interaction:** Numbers animate with a rapid digital "rolling slot-machine" effect on initial dashboard load.

### 4.3 Action Hub (Main Navigation CTAs)
1. **⚡ RUN NEW SIMULATION (Primary CTA):**
   * Background: Cyan-to-dark gradient fill with glowing `#00E5FF` border.
   * Icon: Cyan bolt icon.
2. **📊 SIM HISTORY & ANALYTICS (Secondary CTA):**
   * Background: Translucent obsidian with violet border highlight.
   * Function: Navigates to goldfish turn-to-win distribution curves, mana screw/flood logs, and mulligan trends.
3. **📥 IMPORT DECK (Secondary CTA):**
   * Background: Translucent obsidian with blue border highlight.
4. **🔍 EXPLORE DECKLISTS (Secondary CTA):**
   * Background: Translucent obsidian with neutral gray border highlight.

### 4.4 Data Columns (Frosted Glass Panel)
To guarantee high contrast and legibility over the Dominaria ruin background art:
* **Backdrop Panel:** `rgba(15, 20, 28, 0.85)` dark frosted overlay spanning both activity columns.
* **Left Column — Top Decklists:**
  * Lists top performing decklists (e.g., *Krenko Goblins*, *Drana Vampires*, *Kilo Helm Final*).
  * Color dots (🔴⚫🔵) denote color identity.
  * Win-rate gauges: Gradient teal-to-cyan progress bar sitting inside each deck card, paired with numerical percentage (`69%`, `52%`, `38%`).
* **Right Column — Most Recent Sims:**
  * Real-time match feed showing 4-player pod compositions (e.g., *Kilo vs Wilhelt vs Wyleth vs Drana*).
  * Subtext indicates winner deck, win percentage, game count, and age (`8d ago`, `1d ago`).

---

## 5. 📐 Layout & Structural Grid

```
+-----------------------------------------------------------------------------------+
|                            [🤖 Mascot Robot]                                      |
|                            ARCANE SIM LAB                             [👤 Account]|
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |  ☀️ 52,365          💧 343,621         💀 32,013         🔷 1,121         |  |
|  |  DECKS TESTED       GAMES SIMULATED   COMMANDERS USED    COMBOS DETECTED    |  |
|  +-----------------------------------------------------------------------------+  |
|                                [Calculators & Tools]                              |
|                         What would you like to do today?                          |
|                                                                                   |
|  +------------------+  +-------------------+  +----------------+  +------------+  |
|  | ⚡ RUN NEW SIM   |  | 📊 SIM HISTORY    |  | 📥 IMPORT DECK |  | 🔍 EXPLORE |  |
|  +------------------+  +-------------------+  +----------------+  +------------+  |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  | 🏆 TOP DECKS (Win Rate %)            | ⚡ MOST RECENT SIMS                  |  |
|  |                                      |                                      |  |
|  | 1. Krenko Goblins   [🔴] [██████] 69% | • Kilo vs Wilhelt vs Wyleth          |  |
|  | 2. Drana Vampires   [⚫⚫] [████] 52% |   Wyleth Voltron B3 50% • 8d ago     |  |
|  | 3. Kilo Helm Final  [🔵🔴] [███] 38% | • Kilo Omega vs Meren                |  |
|  +-----------------------------------------------------------------------------+  |
|                                                                                   |
|  +-----------------------------------------------------------------------------+  |
|  |                             MEDIA BLOCK (DISPLAY ADS)                       |  |
|  +-----------------------------------------------------------------------------+  |
|                                                                                   |
|  Sim Lab is unofficial Fan Content permitted under WotC Policy • Scryfall API    |
+-----------------------------------------------------------------------------------+
```

---

## 6. ⚖️ IP Protection & Compliance

To remain strictly compliant with Wizards of the Coast (WotC) Fan Content Policy:
* **No Official Mana Symbols:** Standard WotC mana circle icons ($WUBRG$ symbols) are replaced by custom geometric color dots (🔴, ⚫, 🔵, ☀️, 💧, 💀, 🔥, 🌲).
* **No Trademarked Logos:** "Magic: The Gathering" and "Planeswalker" branding are excluded.
* **Disclaimer Footer:** Included at bottom page margin:
  > *"Sim Lab is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy. Card images via Scryfall. 3,152 rules · 262 keywords."*

---

## 7. 💰 Monetization Integration

* **Media Block Placement:** A full-width white display ad container (`MEDIA BLOCK`) is permanently anchored above the footer.
* **Design Consideration:** The high-contrast white box is intentionally isolated from the dark-mode game interface to fulfill display ad network visibility requirements without obscuring gameplay analytics.
