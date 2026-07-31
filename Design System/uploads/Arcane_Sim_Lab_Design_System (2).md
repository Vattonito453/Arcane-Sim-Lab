# 🧙‍♂️ Arcane Sim Lab — Design System & UI Specification

Welcome to the official Design System specification for **Arcane Sim Lab** (formerly *Magic Sim Lab*), an automated playtesting, goldfish simulation, and matchup analytics platform for *Magic: The Gathering* (specifically Commander/EDH).

This document outlines the visual language, typography, color palette, component specs, layout grid, SVG/icon asset specifications for mana symbols, mascot graphics, and background imagery instructions developed for the platform's home screen and dashboard interface.

---

## 📄 Table of Contents
1. [Brand Identity & Core Concept](#1-brand-identity--core-concept)
2. [Masthead Logo & Mascot Specification](#2-masthead-logo--mascot-specification)
3. [Background Imagery Specifications](#3-background-imagery-specifications)
4. [Color Palette & Tokens](#4-color-palette--tokens)
5. [Mana Symbol & Iconography System](#5-mana-symbol--iconography-system)
6. [Typography Hierarchy](#6-typography-hierarchy)
7. [Component Specifications](#7-component-specifications)
8. [Layout & Structural Grid](#8-layout--structural-grid)
9. [IP Protection & Compliance](#9-ip-protection--compliance)
10. [Monetization Integration](#10-monetization-integration)

---

## 1. 🛡️ Brand Identity & Core Concept

### 1.1 Thematic Vision: "Arcane Automation"
* **Environment:** Set against a backdrop reminiscent of **Dominaria** — featuring ancient floating hedron monoliths, moss-covered stone ruins, and ambient blue-violet mana leyline currents flowing through the sky.
* **Tone:** Equal parts **high fantasy** (evoking classical MTG lore) and **scientific precision** (emphasizing powerful automated goldfish and matchup simulation engines).

---

## 2. 🤖 Masthead Logo & Mascot Specification

### 2.1 Logo Integration & Placement
* **Positioning:** Placed prominently in the upper-center masthead directly above the main title (`ARCANE SIM LAB`).
* **Visual Concept:** Features a friendly, magical brass-and-bronze artifact robot creature seated at the top of the header interface.
* **Character Expression & Pose:**
  * **Personality:** Cheerful, joyful, and eager — designed to look happiest when actively engaged in playing *Magic: The Gathering* matches.
  * **Interaction:** Holds a fan of MTG cards in its metallic hands, glowing with subtle cyan and purple arcane energy from its internal mechanical joints and eyes.
* **Masthead Association:** The robot mascot is directly paired with the `ARCANE SIM LAB` typography (removing previous standalone sub-titles) to form a unified primary brand identity.

### 2.2 Mascot Asset Rendering & Inline SVG Template
To ensure code generators rendering this spec retain the exact artifact-robot aesthetic without converting it into generic clipart, use the following SVG definition:

```html
<!-- ARCANE ROBOT MASCOT MASTHEAD SVG -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120" width="120" height="120" class="masthead-robot-mascot">
  <defs>
    <!-- Brass/Bronze Gradient -->
    <linearGradient id="brassMetallic" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#F59E0B" />
      <stop offset="50%" stop-color="#D97706" />
      <stop offset="100%" stop-color="#78350F" />
    </linearGradient>
    <!-- Cyan Arcane Glow Gradient -->
    <radialGradient id="arcaneCyanGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#00E5FF" stop-opacity="1" />
      <stop offset="70%" stop-color="#00E5FF" stop-opacity="0.4" />
      <stop offset="100%" stop-color="#00E5FF" stop-opacity="0" />
    </radialGradient>
    <!-- Violet Energy Gradient -->
    <radialGradient id="arcaneVioletGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#C084FC" stop-opacity="1" />
      <stop offset="100%" stop-color="#A855F7" stop-opacity="0" />
    </radialGradient>
  </defs>

  <!-- Arcane Aura Ring behind Head -->
  <circle cx="60" cy="45" r="38" fill="url(#arcaneCyanGlow)" opacity="0.6" />
  <circle cx="60" cy="45" r="28" stroke="#00E5FF" stroke-width="1.5" stroke-dasharray="3,3" fill="none" opacity="0.8" />

  <!-- Robot Head Frame (Brass) -->
  <rect x="36" y="22" width="48" height="42" rx="14" fill="url(#brassMetallic)" stroke="#FDE68A" stroke-width="2" />
  <!-- Ear Bolts / Joints -->
  <circle cx="32" cy="43" r="5" fill="#D97706" stroke="#78350F" stroke-width="1.5" />
  <circle cx="88" cy="43" r="5" fill="#D97706" stroke="#78350F" stroke-width="1.5" />

  <!-- Expressive Glowing Eye Visor -->
  <rect x="42" y="32" width="36" height="16" rx="8" fill="#0D0F12" stroke="#00E5FF" stroke-width="1" />
  <ellipse cx="50" cy="40" rx="4" ry="5" fill="#00E5FF" />
  <ellipse cx="70" cy="40" rx="4" ry="5" fill="#00E5FF" />
  <circle cx="51" cy="38" r="1.5" fill="#FFFFFF" />
  <circle cx="71" cy="38" r="1.5" fill="#FFFFFF" />

  <!-- Happy Smiling Mouth Grid -->
  <path d="M 48 54 Q 60 62 72 54" stroke="#F59E0B" stroke-width="2.5" fill="none" stroke-linecap="round" />

  <!-- Brass Torso & Arms Sitting Pose -->
  <path d="M 40 68 L 80 68 L 76 92 L 44 92 Z" fill="url(#brassMetallic)" stroke="#78350F" stroke-width="1.5" />
  <circle cx="60" cy="80" r="6" fill="#00E5FF" opacity="0.9" />

  <!-- Hands Holding Fan of MTG Cards -->
  <!-- Card 1 (Left) -->
  <rect x="42" y="70" width="12" height="18" rx="2" fill="#1E293B" stroke="#00E5FF" stroke-width="1" transform="rotate(-20 48 79)" />
  <!-- Card 2 (Center) -->
  <rect x="54" y="67" width="12" height="18" rx="2" fill="#1E293B" stroke="#A855F7" stroke-width="1" transform="rotate(0 60 76)" />
  <!-- Card 3 (Right) -->
  <rect x="66" y="70" width="12" height="18" rx="2" fill="#1E293B" stroke="#EF4444" stroke-width="1" transform="rotate(20 72 79)" />
  
  <!-- Robot Brass Hands -->
  <circle cx="42" cy="82" r="4" fill="#D97706" />
  <circle cx="78" cy="82" r="4" fill="#D97706" />
</svg>
```

---

## 3. 🖼️ Background Imagery Specifications

### 3.1 Art Direction & Environmental Themes
* **Theme:** High-fantasy landscape inspired by the plane of **Dominaria**.
* **Visual Elements:** Ancient moss-covered stone archways and ruins, floating diamond/hedron stone monoliths drifting through an atmospheric sky, with subtle glowing blue/violet mana leylines in the atmosphere.
* **Color Temperature:** Cool slate blues, deep emerald moss greens, and warm cyan/violet horizon glows.

### 3.2 Global CSS Background Layer Specification
To force code generators (Claude, HTML/CSS engines) to render and maintain the Dominaria background environment across all pages, include the following CSS rules:

```css
/* GLOBAL BACKGROUND ENVIRONMENT SPECIFICATION */
body, .app-root {
  background-color: #0D0F12;
  background-image: 
    radial-gradient(circle at 50% 20%, rgba(0, 229, 255, 0.15) 0%, transparent 60%),
    radial-gradient(circle at 80% 80%, rgba(168, 85, 247, 0.1) 0%, transparent 50%),
    url('https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=1920&q=80'); /* Dominaria Ruin Fallback/Asset */
  background-size: cover;
  background-position: center top;
  background-attachment: fixed;
  background-repeat: no-repeat;
  min-height: 100vh;
}

/* READABILITY OVERLAY PANELS */
.glass-panel, .content-container {
  background: rgba(15, 20, 28, 0.85) !important;
  backdrop-filter: blur(12px) saturate(140%) !important;
  -webkit-backdrop-filter: blur(12px) saturate(140%) !important;
  border: 1px solid rgba(56, 189, 248, 0.25) !important;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.1) !important;
  border-radius: 12px;
}
```

### 3.3 Background Prompt Reference
> *"High-fantasy landscape of ancient overgrown stone ruins on Dominaria, floating diamond monoliths in the sky, mystical mana leyline energy swirling in clouds, twilight lighting, epic atmospheric mood, dark fantasy UI background style --ar 16:9 --v 6.0"*

---

## 4. 🎨 Color Palette & Tokens

The UI utilizes a dark-mode base paired with high-contrast glowing accents to maintain readability over rich environmental artwork while preserving the feel of the five MTG colors ($WUBRG$).

### 4.1 Base & Surface Colors
| Token Name | Hex Code / Value | Visual Use / Description |
| :--- | :--- | :--- |
| `--bg-void` | `#0D0F12` | Deep background base behind environmental art. |
| `--surface-obsidian` | `#161B22` | Card backgrounds, search inputs, and dark panels. |
| `--surface-glass-dark` | `rgba(15, 20, 28, 0.85)` | Dark frosted glass backdrop for data readability over background art. |
| `--surface-glass-border`| `rgba(56, 189, 248, 0.25)` | Subtle glowing border for main content panels. |

### 4.2 Accent & Glow Effects
| Token Name | Hex Code | Visual Use / Description |
| :--- | :--- | :--- |
| `--mana-cyan` | `#00E5FF` | Primary CTA glowing borders, data pulses, active states. |
| `--arcane-violet` | `#A855F7` | Secondary accents, spell energy, interactive highlights. |
| `--glow-cyan-cyan` | `0 0 15px rgba(0, 229, 255, 0.5)` | Box-shadow glow for the "Run New Simulation" button. |

---

## 5. 🔮 Mana Symbol & Iconography System

To prevent automated systems from rendering generic, flat clip-art emoji icons, use custom layered SVG badges with inner glow effects for color identities ($WUBRG$).

### 5.1 SVG Mana Badge Specifications

```html
<!-- WHITE MANA BADGE (SUN) -->
<svg width="20" height="20" viewBox="0 0 24 24" class="mana-badge mana-white">
  <circle cx="12" cy="12" r="11" fill="#292010" stroke="#F59E0B" stroke-width="1.5" />
  <circle cx="12" cy="12" r="4" fill="#FDE68A" />
  <path d="M12 3v3 M12 18v3 M3 12h3 M18 12h3 M5.6 5.6l2.1 2.1 M16.3 16.3l2.1 2.1 M5.6 18.4l2.1-2.1 M16.3 7.7l2.1-2.1" stroke="#F59E0B" stroke-width="1.5" stroke-linecap="round" />
</svg>

<!-- BLUE MANA BADGE (DROPLET) -->
<svg width="20" height="20" viewBox="0 0 24 24" class="mana-badge mana-blue">
  <circle cx="12" cy="12" r="11" fill="#092537" stroke="#00E5FF" stroke-width="1.5" />
  <path d="M12 4 C12 4 6 11 6 15 A6 6 0 0 0 18 15 C18 11 12 4 12 4 Z" fill="#00E5FF" />
</svg>

<!-- BLACK MANA BADGE (SKULL IDENTITY) -->
<svg width="20" height="20" viewBox="0 0 24 24" class="mana-badge mana-black">
  <circle cx="12" cy="12" r="11" fill="#1D1526" stroke="#A855F7" stroke-width="1.5" />
  <path d="M8 10 a4 4 0 0 1 8 0 c0 3 -1.5 4 -2 6 h-4 c-.5 -2 -2 -3 -2 -6 Z" fill="#C084FC" />
  <circle cx="10" cy="10" r="1" fill="#1D1526" />
  <circle cx="14" cy="10" r="1" fill="#1D1526" />
</svg>

<!-- RED MANA BADGE (FLAME) -->
<svg width="20" height="20" viewBox="0 0 24 24" class="mana-badge mana-red">
  <circle cx="12" cy="12" r="11" fill="#331414" stroke="#EF4444" stroke-width="1.5" />
  <path d="M12 4 C10 8 7 10 7 14 A5 5 0 0 0 17 14 C17 10 14 8 12 4 Z" fill="#F87171" />
  <path d="M12 9 C11 11 9.5 12 9.5 14 A2.5 2.5 0 0 0 14.5 14 C14.5 12 13 11 12 9 Z" fill="#FEF08A" />
</svg>

<!-- GREEN MANA BADGE (TREE / LEAF) -->
<svg width="20" height="20" viewBox="0 0 24 24" class="mana-badge mana-green">
  <circle cx="12" cy="12" r="11" fill="#0B261A" stroke="#10B981" stroke-width="1.5" />
  <path d="M12 4 C8 8 6 12 6 16 h12 C18 12 16 8 12 4 Z" fill="#34D399" />
  <line x1="12" y1="9" x2="12" y2="18" stroke="#0B261A" stroke-width="1.5" />
</svg>
```

---

## 6. 🔤 Typography Hierarchy

The typographic system pairs high-fantasy serif headings with clean, modern monospaced and sans-serif fonts for data precision.

| Role | Font Family | Size / Weight | Application |
| :--- | :--- | :--- | :--- |
| **Primary Logo Title** | Serif (e.g., *Cinzel*, *Trajan*) | `28pt / Bold / Uppercase` | `ARCANE SIM LAB` Main Title |
| **Section Headers** | Serif / Semi-Bold | `16pt - 18pt / Semi-Bold` | Section Headings (`Top decklists`, `Most recent sims`) |
| **CTA Buttons** | Geometric Sans / Bold | `12pt - 14pt / Bold / All-Caps` | Action Buttons (`RUN NEW SIMULATION`) |
| **Data & Statistics** | Monospace (e.g., *JetBrains Mono*) | `11pt - 13pt / Regular` | Rolling Tallies, Percentages, Timestamps |
| **Body / Meta Text** | Clean Sans-Serif | `10pt - 11pt / Regular` | Deck Names, Subtitles, Rules Engine Footer |

---

## 7. 🧩 Component Specifications

### 7.1 Masthead & Header Section
* **Mascot Placement:** Seated directly above the `ARCANE SIM LAB` title bar.
* **Account Widget:** Positioned top-right (`VD Account ˅`), formatted as a translucent pill button with a user avatar icon.

### 7.2 The Rolling Tally Banner
* **Container:** Dark metallic instrument bar (`#111827`) with rounded corners and subtle border stroke.
* **Live Counters:**
  * ☀️ `52,365 decks tested`
  * 💧 `343,621 games simulated`
  * 💀 `32,013 commanders used`
  * 🔷 `1,121 infinite combos detected`
* **Interaction:** Numbers animate with a rapid digital "rolling slot-machine" effect on initial dashboard load.

### 7.3 Action Hub (Main Navigation CTAs)
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

### 7.4 Data Columns (Frosted Glass Panel)
To guarantee high contrast and legibility over the Dominaria ruin background art:
* **Backdrop Panel:** `rgba(15, 20, 28, 0.85)` dark frosted overlay spanning both activity columns with `backdrop-filter: blur(12px)`.
* **Left Column — Top Decklists:**
  * Lists top performing decklists (e.g., *Krenko Goblins*, *Drana Vampires*, *Kilo Helm Final*).
  * Color SVG badges denote color identity.
  * Win-rate gauges: Gradient teal-to-cyan progress bar sitting inside each deck card, paired with numerical percentage (`69%`, `52%`, `38%`).
* **Right Column — Most Recent Sims:**
  * Real-time match feed showing 4-player pod compositions (e.g., *Kilo vs Wilhelt vs Wyleth vs Drana*).
  * Subtext indicates winner deck, win percentage, game count, and age (`8d ago`, `1d ago`).

---

## 8. 📐 Layout & Structural Grid

```
+-----------------------------------------------------------------------------------+
|                     [🤖 Magical Robot Mascot Masthead]                            |
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

## 9. ⚖️ IP Protection & Compliance

To remain strictly compliant with Wizards of the Coast (WotC) Fan Content Policy:
* **No Official Mana Symbols:** Standard WotC mana circle icons ($WUBRG$ symbols) are replaced by custom geometric SVG badges.
* **No Trademarked Logos:** "Magic: The Gathering" and "Planeswalker" branding are excluded.
* **Disclaimer Footer:** Included at bottom page margin:
  > *"Sim Lab is unofficial Fan Content permitted under the Wizards of the Coast Fan Content Policy. Card images via Scryfall. 3,152 rules · 262 keywords."*

---

## 10. 💰 Monetization Integration

* **Media Block Placement:** A full-width white display ad container (`MEDIA BLOCK`) is permanently anchored above the footer.
* **Design Consideration:** The high-contrast white box is intentionally isolated from the dark-mode game interface to fulfill display ad network visibility requirements without obscuring gameplay analytics.
