# UI.md: Dark Amber Glass Design System (Desktop Adaptation)

Source: two mobile screens (AI Tools Hub, Team Space). Goal: reproduce the same look and feel as a desktop app, and provide a recipe for reskinning any application into it.

Style summary: near-black warm charcoal surfaces, soft raised "glass-clay" cards, a single amber/bronze accent family, one coral-pink gradient hero action, and soft inner highlights instead of hard borders. Font: a subtle serif or humanist AI-lab face (e.g. Newsreader / Source Serif 4 for headings, Inter or Geist for dense UI text).

---

## 1. Colour Tokens

### 1.1 Surfaces (warm charcoal, never pure grey)

| Token | Hex | Used for |
|---|---|---|
| `--bg-app` | `#0B0B0C` | Window background behind everything |
| `--bg-canvas` | `#1C1C1E` | Main app shell / panel body |
| `--bg-card` | `#242426` | Tool tiles, member cards, project cards |
| `--bg-card-hover` | `#2B2B2E` | Hover state of cards |
| `--bg-inset` | `#18181A` | Progress tracks, search wells, input interiors |
| `--bg-chip-icon` | `#333336` | Square icon holders (back button, tool icons) |
| `--bg-dock` | `#26282C` | Bottom nav pill (slightly cooler than cards) |

### 1.2 Text

| Token | Hex | Used for |
|---|---|---|
| `--text-primary` | `#F5F2EE` | Titles ("AI Tools Hub", tile names, member names) |
| `--text-secondary` | `#A9A5A0` | Subtitles, roles, "4 members", descriptions |
| `--text-tertiary` | `#6F6C68` | Timestamps, "View All", faded items |
| `--text-on-accent` | `#FFF4E6` | Text on amber buttons/banners |
| `--text-on-hero` | `#FFFFFF` | Icon on coral CTA |

Text is warm off-white, never `#FFF`, to avoid glare on dark.

### 1.3 Accent: Amber / Bronze family (the "orange")

| Token | Hex | Role |
|---|---|---|
| `--amber-300` | `#F2A93B` | Brightest: credit badge, batch-processing bolt chip |
| `--amber-500` | `#D98A1E` | Icon-chip gradient base |
| `--amber-700` | `#8A5A2B` | Banner/button gradient light end |
| `--amber-800` | `#6B4423` | Gradient mid |
| `--amber-900` | `#3A2616` | Gradient dark end, blends into surface |

### 1.4 Hero CTA: Coral gradient

| Token | Hex |
|---|---|
| `--coral-start` | `#FF7B7B` |
| `--coral-end` | `#E8506A` |

### 1.5 Status

| Token | Hex | Used for |
|---|---|---|
| `--online` | `#34D058` | Presence dot on avatars |
| `--completed-bg` | `#8A5A2B` to `#6B4423` | "Completed" pill |
| `--progress-bg` | `#9A6430` to `#6B4423` | "My Progress" pill |

---

## 2. Gradients (how they progress)

All amber gradients run **left to right, light bronze to dark charcoal-brown**, so the right end dissolves into the card surface. This is the signature of the look.

```css
/* Search bar + Batch banner: wide horizontal bronze wash */
--grad-amber-wide: linear-gradient(90deg, #8A5A2B 0%, #6B4423 45%, #4A301B 100%);

/* Join Session / My Progress / Completed pills: shorter, brighter */
--grad-amber-pill: linear-gradient(135deg, #9A6430 0%, #6B4423 100%);

/* Credit badge + bolt chip: saturated orange tile */
--grad-amber-chip: linear-gradient(145deg, #F7B648 0%, #D98A1E 100%);

/* Hero CTA: coral, diagonal */
--grad-coral: linear-gradient(145deg, #FF8A80 0%, #F0566B 100%);

/* Credit progress track: dark metal sheen, left lighter, right darker, knob at end */
--grad-track: linear-gradient(90deg, #3A3A3D 0%, #1E1E20 100%);
```

Rules:
1. Never go amber to another hue. Stay inside brown/orange. Coral is reserved for the single primary action.
2. Gradient end color must be within ~10% luminance of `--bg-card` so edges feel melted, not boxed.
3. Add a 1px top highlight (see Section 4) on every gradient surface.

---

## 3. Components

### 3.1 Layout shell (desktop)

- Window: 1440x900 reference. Background `--bg-app`.
- Left rail (replaces mobile bottom bar option) or floating bottom dock (keep the mobile feel). Recommended: **floating bottom-center dock**, as in the source.
- Main content: max-width 1120px, centered, 24px gutters, 12-col grid.
- Mobile 2-col tool grid becomes 3 or 4 columns at 1440px.
- Page header: back button (left), centered title + subtitle, utility icon button (right).

### 3.2 Header

- Back and utility buttons: 44x44, radius 14px, `--bg-chip-icon`, 1px inner highlight, icon `--text-primary` at 1.75px stroke.
- Title: 20px / 600, `--text-primary`. Subtitle: 13px / 400, `--text-secondary`.
- Right button icons: magic wand (AI hub), people (team space).

### 3.3 Credits card

- Container: `--bg-card`, radius 20px, padding 16px, subtle amber glow on top edge.
- Label "AI Credits Remaining": 13px `--text-secondary`.
- Value "2,450": 28px / 600 `--text-primary`.
- Badge (top right): 40x40, radius 12px, `--grad-amber-chip`, white diamond/gem glyph (sparkle-square), outer glow `0 0 20px rgba(242,169,59,.35)`.
- Progress track: height 36px, radius 18px, `--bg-inset`, inner shadow. Fill uses `--grad-track` with a circular dark knob (28px) at the fill end carrying a faint highlight. Fill ~70%.

### 3.4 Search bar (amber wash)

- Height 52px, radius 18px, `--grad-amber-wide`.
- Leading icon: frame/viewfinder glyph, `--text-on-accent`.
- Placeholder: "Search AI tools", 15px, `--text-on-accent` at 85%.
- Desktop: add `Ctrl/Cmd+K` hint chip on the right, `rgba(255,255,255,.12)`.

### 3.5 Tool tile (the core card)

- Size: fills grid cell, min-height 150px, radius 22px, padding 18px.
- Background `--bg-card`, glass treatment from Section 4.
- Icon holder (top-left): 48x48, radius 14px, `--bg-chip-icon`, glossy glass (Section 4).
- Icon: 24px, stroke 1.75, `--text-primary`.
- Title: 17px / 600 `--text-primary`. Description: 14px `--text-secondary`.
- Hover: lift 2px, bg `--bg-card-hover`, icon-holder glow intensifies.

Tool to icon mapping (line icons, Lucide-style):

| Tool | Icon |
|---|---|
| Auto Subtitles | Bold "T" in square |
| Script to Video | Video camera / clapper with doc |
| Voice Cloning | Microphone |
| BG Remover | Paint bucket with drop |
| Thumbnails | Image in rounded square |
| Viral Reels | Lightning bolt in rounded square |

### 3.6 Feature banner ("New: Batch Processing")

- Full-width, height 76px, radius 22px, `--grad-amber-wide`.
- Left chip: 44x44, radius 12px, `--grad-amber-chip`, white filled bolt.
- Title 20px / 600 `--text-on-accent`; sub 14px at 85%.
- Right: ghost button "Try", 36px tall, radius 18px, bg `rgba(255,255,255,.10)`, text `--text-primary`.

### 3.7 Primary CTA (floating action)

- 88x88 on mobile; **64x64 on desktop**, radius 24px, `--grad-coral`.
- Glyph: white 4-point sparkle (AI hub) or people icon (team space). The glyph changes per screen to reflect that screen's primary action.
- Shadow: `0 10px 30px rgba(240,86,107,.35)`, inner top highlight `inset 0 1px 0 rgba(255,255,255,.35)`.
- Sits to the right of the dock, same baseline.

### 3.8 Bottom dock (nav bar)

- Floating pill, height 64px, radius 24px, `--bg-dock`, 1px border `rgba(255,255,255,.06)`, blur backdrop.
- 5 icons, 24px, evenly spaced, inactive `--text-primary` at 90%.
- Order: Home, Edit (scissors), Analytics (bar chart in square) / AI (sparkle), Team (people), Profile (person).
- The active destination swaps with the CTA: on AI Hub the sparkle moves out to the CTA and Analytics sits in the dock; on Team Space the people icon moves to the CTA and sparkle sits in the dock. Rule: **the current section's icon becomes the coral CTA**.
- Active indicator alternative for desktop: 2px amber underline glow below icon.

### 3.9 Team Space

- "Active Now" block: title 24px / 600; sub 14px `--text-secondary`; avatar stack right (overlapping 40px circles, 2px `--bg-canvas` ring, "6+" overflow in `--bg-card`).
- "Join Session" button: pill, height 48, radius 24, `--grad-amber-pill`, text `--text-on-accent` 16px / 500, soft outer glow `0 6px 20px rgba(138,90,43,.35)`.
- Member card: `--bg-card`, radius 20px, 56px circular avatar, name 17px / 600, role 14px `--text-secondary`, green presence dot (12px, `--online`, 2px card-colored ring) bottom-right of avatar. 2-col grid (4 on wide desktop).
- Section headers ("Team Members", "Shared Projects", "Recent Activity"): 24px / 600. "View All": 14px `--text-tertiary`, right aligned.
- Project card: `--bg-card`, radius 22px. Title 20px / 600, members line with people glyph. Status pill top-right ("My Progress" `--grad-amber-pill`, "Completed" slightly darker). Progress track: 48px tall inset pill filled with fine vertical tick marks (like an audio waveform / equalizer), ticks `#3A3A3D`, 2px wide, 3px gap; the filled portion uses amber ticks.
- Activity row: folder icon in glass chip, text 16px, faded sub-text, right-aligned clock icon + "2m ago" `--text-secondary`. Rows fade out toward the dock via a bottom mask gradient.

---

## 4. Liquid Glass Treatment (the glow around icons and folders)

Apply to icon holders, folder chips, dock, and CTA.

```css
.glass-chip {
  background:
    radial-gradient(120% 120% at 30% 0%, rgba(255,255,255,.14) 0%, rgba(255,255,255,0) 55%),
    var(--bg-chip-icon);
  border-radius: 14px;
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.18),      /* top specular edge */
    inset 0 -1px 0 rgba(0,0,0,.45),           /* bottom depth */
    0 0 0 1px rgba(255,255,255,.04),          /* hairline */
    0 8px 20px rgba(0,0,0,.45);               /* ambient drop */
  backdrop-filter: blur(16px) saturate(140%);
}
.glass-card {
  background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,0)), var(--bg-card);
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.07),
    inset 0 0 24px rgba(255,255,255,.015),
    0 12px 32px rgba(0,0,0,.35);
}
.amber-glow { box-shadow: 0 0 24px rgba(242,169,59,.30), inset 0 1px 0 rgba(255,255,255,.35); }
```

Key traits: light comes from top-left; every element has a 1px top specular line, a darker bottom line, and a very soft ambient halo. No hard strokes. Cards feel like soft-touch plastic with a faint wet sheen.

---

## 5. Spacing, Radius, Elevation

- Spacing scale: 4, 8, 12, 16, 20, 24, 32, 40.
- Radius: chips 12 to 14, cards 20 to 22, pills 999, dock 24, CTA 24.
- Grid gap between tiles: 16px. Section gap: 32px.
- Elevation levels: L0 app bg; L1 canvas; L2 cards; L3 chips/dock; L4 CTA (strongest shadow + colored glow).

## 6. Typography

- Headings: subtle serif (Newsreader, Source Serif 4, or Fraunces at low optical weirdness), 600.
- UI/body: Inter or Geist, 400 and 500.
- Scale: 13 caption, 14 body-sm, 16 body, 17 card title, 20 section/title, 24 section header, 28 metric.
- Letter-spacing: -0.01em on titles. Numbers use tabular-nums.

## 7. Motion

- Hover/press: 140ms ease-out; press scales to 0.98.
- Glow breathing on the CTA: 3s ease-in-out, shadow opacity .30 to .45.
- Presence dots pulse once on state change.
- Progress ticks fill left to right in 40ms stagger.
- Page transitions: 200ms fade + 8px upward slide.

## 8. Converting ANY application into this UI

1. **Re-skin surfaces.** Map every background to `--bg-app`, `--bg-canvas`, `--bg-card`, `--bg-inset`. Delete all borders; replace with the Section 4 inner highlights.
2. **Card everything.** Each feature, list item, or setting becomes a rounded glass card with an icon chip, bold title, grey description.
3. **Pick one accent.** Replace brand colors with the amber family for all secondary actions, banners, pills, and search.
4. **Pick one hero action per screen.** Render it as the coral gradient CTA; its icon equals the section icon.
5. **Dock navigation.** Reduce top-level nav to 5 icons in a floating pill; no text labels.
6. **Header pattern.** Back button, centered title with one-line subtitle, one utility icon.
7. **Progress as texture.** Replace plain bars with tick-mark or knob tracks.
8. **Status through pills.** All state (Completed, In Progress, New) uses amber pills, never red/green text, except the presence dot.
9. **Icons.** Single stroke weight (1.75px), rounded caps, 24px, always inside a glass chip.
10. **Contrast check.** Body text on any amber surface must hit 4.5:1; use `--text-on-accent`.

## 9. Do / Don't

- Do keep the amber gradient fading into the surface on its right edge.
- Do use glow only on amber and coral elements.
- Don't use pure black cards, pure white text, or more than one saturated hue family.
- Don't put glass over busy imagery; keep it over flat dark surfaces.

---

## Latest (design trends relevant to this style)

- Dark mode is increasingly treated as the default primary surface for premium products, not a toggle.
- Glassmorphism is trending again in 2026, with Apple's Liquid Glass (refracting, specular edges) pushing it further; guidance is to use it sparingly and keep strong text contrast.
- "Dark glassmorphism over ambient gradients" is called out as a leading 2026 style for AI, music and crypto apps.
- Gradients appear in roughly 40% of top-chart apps, especially in icons.
- Motion is now treated as a core UI language rather than decoration.