# Epoch — brand and product experience specification

Status: proposed design specification for implementation; no UI has been built from this document. This document defines the **layout, hierarchy, copy and interaction behaviour** for the Retention Predictor. The [PRD](PRD.md) owns product scope, [Schema](Schema.md) owns data, and [UI reference](UI_REFERENCE.md) owns the original dark amber palette. If a decorative component in the UI reference conflicts with clarity here, use this document's interaction rule while preserving the reference's visual language.

## 1. The idea the interface must communicate

Epoch is a video review desk. Its job is to help a creator answer: **where might viewers leave, what evidence suggests that, and what exact edit could help?** It should feel calm, editorial and precise. It is not a wall of telemetry, a generic AI chat page, or a video editor that pretends to render a finished cut.

The screenshot supplied with this request is a useful **density anti-reference**: a source area and a permanently open assistant area each contain multiple full sections, repeated statuses, alerts and an action panel. Epoch must not copy that composition or its unrelated vendor workflow. At any moment, the creator should have one primary task, one primary action, and a small amount of supporting context. Further evidence is available on demand.

Three brand qualities guide every screen:

- **Evidence first.** A finding points to a time, a quote, a frame or a measurement. A visual claim never appears as unsupported prose.
- **Editorial, not alarmist.** Explain an opportunity to improve; do not paint every long shot or pause as a fault.
- **Honest about prediction.** Risk, assumed retention scenarios and observed audience data have different names, scales and treatments.

The product's recurring sentence pattern is **Observation → Why it matters → Proposed edit**. An issue card may start with a short title, but its expanded state must answer those three questions and show the source.

## 2. Navigation and information architecture

Global destinations are **Projects**, **New analysis**, **Review**, and **Results**. Profile/settings live behind a header control, not a fifth prominent destination. Within an opened project, use a compact subnavigation: **Overview**, **Transcript**, **Shots**, **Retention**, **Edit plan**. Results holds project reports, evaluation and version comparisons; a project-specific Results link is also reachable from Retention and Edit plan. Do not make the user choose between similarly named “Analytics,” “Insights,” “Results” and “Report” pages that show the same facts.

Use the floating bottom dock from the supplied visual guide for the four global destinations. Give every icon a visible label on hover/focus and an accessible name at all times; the active destination has a short persistent label. The dock must never cover timeline controls: reserve at least 96 px of scrollable bottom space. In an immersive video focus mode the dock can recede, with a visible way back. A project page keeps a small title/breadcrumb and run selector above its local tabs.

The user should always know these four things without opening a menu: **which video**, **which analysis run**, **which moment**, and **whether that moment was inspected**. Other metadata belongs in an expandable Run details panel.

## 3. Progressive disclosure rules

| Layer | Visible by default | Revealed by interaction |
|---|---|---|
| Project library | Project title, thumbnail/placeholder, latest status, last activity, one next step | All runs, technical provenance, import log |
| Project header | Title, category, active run, overall coverage state | Model revision, environment, file hashes, full stage list |
| Overview | Player, one selected context panel, timeline, three priority findings | Complete issue list, all measured signals, chat history |
| Finding | One-line observation, time range, status, proposed action | Full quote, frames, metrics, counter-explanation, other related findings |
| Transcript | Current passage and nearby context, lightweight margin markers | Whole-text search results, passage comparison, detailed semantic labels |
| Shots | Filmstrip and selected shot's most relevant property | Full measurements, OCR samples, frame inspection, alternate observations |
| Retention | One chart mode, assumptions label, three meaningful metrics | Sensitivity, all tracks, formula/provenance and per-bin numbers |
| Assistant | Closed by default; small Ask about this moment affordance | Conversation drawer and cited answers |

Hard density budget for a 1440 × 900 review viewport: **one main chart or video**, at most **three summary values**, at most **three expanded priority insights**, **one expanded warning**, and **one primary button**. Lists can have more rows below the fold; they must not all demand equal visual weight. Do not truncate source evidence invisibly. Show a concise preview plus a deliberate “View evidence” expansion.

Warnings are grouped by cause. A failed OCR stage produces one status explanation with affected coverage, not a toast, banner, card and repeated row icon. Dismissal only hides presentation; it does not alter evidence or scoring.

## 4. Visual language and tokens

Use the source guide's warm charcoal layers: app `#0B0B0C`, canvas `#1C1C1E`, card `#242426`, inset `#18181A`, primary text `#F5F2EE`, secondary text `#A9A5A0`, amber `#D98A1E`, and the coral hero gradient `#FF7B7B` → `#E8506A`. Keep the source guide intact as a visual reference. This document narrows how often those treatments appear.

Amber means **selection or a meaningful highlight**, not “everything interactive.” Use it for the current time cursor, selected issue edge, active local tab and an occasional emphasis word. Coral is reserved for the **single primary action** on a screen, such as New analysis or Import result. Do not place coral gradients on every card. Severity needs a text label and icon/pattern; it cannot be inferred from orange versus red alone. Technical errors use subdued status styling and clear language, without turning the whole page into red panels.

Use Source Serif 4 for sparse display headings and Inter for controls, charts, transcript and dense data. Bundle a tested Noto Sans Devanagari fallback so Hindi remains legible. A transcript quote uses ordinary sentence case and comfortable line height; avoid all-caps analysis labels. Essential times, statuses and chart axes use primary or secondary text, never the reference's low-contrast tertiary colour without testing.

At the reference desktop size, centre a maximum 1120 px content canvas with 24 px outer gutters and a 12-column grid. Cards generally use 20–22 px radius, but analytical rows and tables can use simpler dividers to reduce nested-card noise. Use soft top highlights and restrained glass effects; no heavy blur behind transcript text. A timeline needs crisp 1 px lines and readable tooltips more than ornamental glow. Spacing steps: 4, 8, 12, 16, 24, 32, 48 px. The default page has generous vertical breathing room; do not solve density by shrinking every label.

Motion is functional and optional: a drawer slides once, a selected interval highlights, and playback follows the transcript. No looping gradients, pulsing risk badges, animated score counting, or chart motion that makes exact values harder to read. Respect reduced-motion preferences. Loading progress should show stage names and known completion, not fake percentage animation.

## 5. Screen specifications

### 5.1 Projects / dashboard

The first screen answers **what can I review next?** Header: “Your videos” plus the coral New analysis button. Under it, a restrained row of filters (All, Ready, Needs import, Partial), search, and project cards. A card shows title, 16:9 thumbnail, category/language, analysis status, last worked date and one relevant next action. Avoid a global 1–100 performance score or a portfolio retention graph drawn from four videos.

If there are no projects, show one clear empty state with two choices: Analyse a video and Start with a transcript. If there are unfinished projects, pin **Continue where you left off** as a compact card above the library. If the last run is partial, use “Review available findings” and a small “Visual text was not analysed” note rather than blocking entry.

### 5.2 New analysis / onboarding

Use a short four-step flow with a visible stepper: **Goal → Sources → Check → Process**. Keep one form group expanded at a time. Back navigation preserves entered data.

1. **Goal:** video title or intended title, category, English/Hindi/mixed, and optional intended audience. Explain briefly that the title anchors promise/payoff analysis.
2. **Sources:** choose Video, Transcript/script, or Both. Accept video files for the Colab workflow; accept pasted text, `.txt`, `.md`, `.srt`, `.vtt` for transcript entry. Show one large drop target, then a compact file summary. If both are supplied, ask whether text is an existing timed transcript, an untimed script, or a correction to automated speech recognition. Do not silently assume the script matches the final video word for word.
3. **Check:** show source duration, audio presence, language, title, transcript timing precision, and any mismatch. Corrections are editable here. Errors appear directly beside the affected input.
4. **Process:** script-only can start local text analysis when the configured language model is available. Video shows the true manual sequence: prepare request → upload source/request in Colab → download result ZIP → import it here. The website can keep the project and preview while waiting; it must not present local upload as active GPU analysis.

On the waiting screen, make **Import result ZIP** the one primary action. Offer a small “How to run Colab” expansion and a copyable checklist. Show the project title so the user can match the ZIP. A mismatched ZIP gives a specific error and preserves the project. A valid partial ZIP opens Review with coverage gaps explained.

### 5.3 Review / Overview

The default review layout should not recreate the screenshot's permanently competing assistant panel. Use a two-column top area, then one full-width timeline:

```text
Project title · Active run ▾                         Export ▾
Overview   Transcript   Shots   Retention   Edit plan

┌────────────────────── 7 columns ──────────────────────┐ ┌─ 5 columns ─┐
│ video player, one quiet issue marker overlay           │ │ At this time │
│ playback controls and current source time              │ │ 1 insight    │
└────────────────────────────────────────────────────────┘ │ evidence link│
                                                           └──────────────┘
Full-width linked timeline: playhead / issue bands / coverage / shot ticks
Top three priorities (collapsed rows by default)                 See all
```

“At this time” follows the playhead. It shows the current transcript sentence or issue and an evidence button. If no issue applies, it says what is being explained, or simply shows the transcript; it does not manufacture a “healthy” score. Selecting an issue freezes that panel on the selected interval until the user resumes follow-playback mode. Opening its evidence uses a right-side drawer or modal that temporarily replaces the context panel, not a third permanent column.

The timeline is the shared coordination surface. A click on a finding, transcript word, shot, OCR item, chart marker or chat citation seeks the player and selects a single interval. The cursor and selected interval have different treatments. Use hover for preview and click for persistent selection. Show source time precisely; show estimated timing with a dashed interval and label. The player never autoplays on card hover.

Priority order is first **editorial usefulness**, then severity and time. Each collapsed row displays a short cause, source time, one-line edit and evidence status. Expanding one row collapses the previous row. “See all” opens a filterable issue list with type, modality, status and time filters; the default viewport does not show all 64 possible signals.

### 5.4 Transcript

Keep a compact sticky player or player mini-view and a generous reading column. The transcript follows playback, but manual scrolling pauses follow mode and reveals a **Return to playhead** control. Use a narrow semantic margin rather than colouring every word: promise, answer, repeat, tangent, definition, example, CTA. A legend is tucked into a layer menu; each layer can be toggled.

Selecting a passage opens a contextual menu: Explain concern, Compare with earlier passage, Suggest rewrite, Add to plan. Repetition comparison uses two quoted passages side by side in a drawer, with what is genuinely new highlighted. Promise/payoff uses a title-obligation card with setup, partial answer and fulfilled answer links. A code-mixed sentence retains its original wording; translation is an optional reading aid. Unaligned words are selectable as a segment, not falsely clickable at precise word times.

Search results show a few context lines and timestamps; full results open on demand. The transcript should read naturally when all analytical layers are off. No inline AI essay interrupts the original words.

### 5.5 Shots

Use a horizontal filmstrip grouped by detected shots, with a time ruler. A shot tile contains a thumbnail, start time, duration and at most two small markers (for example text present and issue present). Selecting a tile seeks to it and shows a single inspector beneath or beside the filmstrip.

The inspector opens on **Why this shot matters**: its role relative to the spoken point, the most relevant observation, and any counter-evidence. Tabs within it expose **Measured** (cut boundaries, motion, black/freeze, OCR) and **Frames** (the actual sampled images and their times). A long static diagram can explicitly show “Useful static visual: speaker explains the labels,” avoiding a simplistic stagnation alarm. The interface must distinguish a measured shot duration from a VLM interpretation and disclose sparse sampling.

An **Inspect more closely** action creates a targeted rerun request for Colab. Until that result is imported, the UI says “More frames needed to judge this interval.” It never fills the gap with a confident visual description.

### 5.6 Retention / results

The top of this screen has one prominent chart with a segmented switch: **Estimated retention**, **Drop-off risk**, and **Observed data** only when authentic compatible data has been imported. Do not overlay all three incompatible scales by default. Retention always carries “Uncalibrated scenario” beside the title and a visible Assumptions control. Risk shows a heuristic 0–100 scale by modality; it is not labelled a probability.

Under the chart, show three summary values with units: **earliest substantive delivery**, **highest-risk region**, and **evidence coverage**. A secondary summary may show assumed average view duration and end retention once the user acknowledges the scenario assumptions. Unknown intervals appear as a patterned gap/range, never as zero risk. Chart hover gives the interval, dominant issue, source link, sampled coverage and appropriate units.

Below, a ranked **Where to look first** list gives the top five editable intervals. The full data table and formula/provenance live under expandable “Method and data.” The Results report uses the same labels in exported views. If actual retention is imported later, retain its metric definition and original bin resolution rather than drawing false second-by-second certainty.

### 5.7 Edit plan and comparison

The plan is a queue of accepted suggestions, each with operation, source interval, rationale and prerequisites. The top bar shows number of edits, original/proposed duration and unresolved conflicts. A conflict appears next to the two relevant operations, with a clear resolution choice; do not stack generic warning banners at the top.

Comparison has two explicit tabs: **Hypothetical scenario** and **Reanalysed upload**. The first states the assumed resolution and shows changes in title-payoff timing, duration, assumed view duration and assumed percentage viewed. The second compares genuinely separate run versions with coverage and model identity shown. A shorter video can raise percentage viewed while reducing seconds watched, so no single green “improved” badge is allowed. An external-edit export has source timestamps and proposed words, not a promise that Epoch altered the video.

### 5.8 Assistant

The assistant is a **closed-by-default drawer**, summoned from Ask about this moment or a selected passage. The composer shows its scope: current video, current run, selected interval. Suggested questions are contextual, not generic “Ask me anything” filler. An answer starts with a direct response, then expandable cited evidence and an optional proposed action. Citation clicks seek the player. A proposed action has a visible Add to plan button; asking a question alone does not mutate the plan.

If coverage is missing, the assistant says what is unavailable and can offer the rerun request. If the text service is unavailable, the rest of Review continues to work; do not show a spinner indefinitely or replace saved findings with an error page.

### 5.9 Profile, settings and evaluation

Profile is a compact utility page for creator name, default category/language, transcript display preferences, local storage, export/deletion controls and API connection status. It is not a social profile, credit wallet or team-management page. Retention scenario assumptions remain per project/comparison because they materially change that project's chart.

Evaluation lives in Results and shows the demonstration set, language/category coverage, issue annotation counts, sample splits, measured runtime and representative misses. Make “Actual audience retention accuracy: not evaluated” legible until matching audience data exists. Keep technical stage logs and model hashes in Run details, not the opening dashboard.

## 6. States and microcopy

| State | What the user sees | Primary next action |
|---|---|---|
| Empty library | One sentence describing the value and a simple input choice | New analysis |
| Awaiting Colab | The manual three-step handoff and project identity | Import result ZIP |
| Importing | File validation stage and real progress where known | Wait or cancel safely |
| Complete | Coverage badge and first supported finding | Review video |
| Partial | What succeeded, what is unknown, affected timeline regions | Review available results or export rerun |
| No findings | “No supported issues found in inspected regions” plus coverage | Explore transcript/shots |
| Script-only | Estimated timeline and missing visual/audio badges | Add video when available |
| Provider unavailable | Existing evidence remains accessible; chat/text stage identified | Retry once later or review saved analysis |
| Invalid package | Specific mismatch/file/schema error; no partial silent import | Choose correct ZIP or rebuild export |

Use **“Possible issue”** or a concrete editorial description, never “Viewers will definitely leave.” Use **“Not inspected”**, not “No issue.” Use **“Proposed edit”**, not “Fixed.” Use **“Estimated retention under assumptions”**, not “Predicted actual audience retention.” These terms are part of the interface contract, not optional disclaimer text.

## 7. Interaction and accessibility contract

Keyboard users can reach global navigation, player, timeline intervals, cards, drawers and close controls in a logical order. Timeline markers have list equivalents so precision does not depend on pointer hover. Focus is visible against dark surfaces. Minimum target size is 44 px for primary touchable controls. Charts have a text summary and inspectable table; colour is supplemented by labels or patterns. Test the actual text/gradient combinations for contrast rather than trusting token names.

At narrower widths, stack player above context and switch the transcript/shot inspector to a full-width drawer. Do not squeeze three analytical panes into a laptop viewport. A mobile-width view can review saved results, but full editing/shot analysis remains desktop-first for this prototype. Keep selected time, run and tab in URL or recoverable state so back navigation and refresh do not reset the user's investigation.

## 8. Delivery order and design acceptance

**Phase 1:** brand shell, Projects, New analysis, import/waiting states, Overview, finding detail, transcript reading, risk/retention switch. Use simple static transitions. A creator must be able to import one real package, seek from a finding, inspect evidence and understand the curve's assumptions.

**Phase 2:** semantic transcript layers, filmstrip/shot inspector, contextual assistant, edit plan, comparisons and rerun request flow. Add visual embellishment only after the linked-selection interaction works reliably.

**Phase 3:** evaluation/report screens, graceful offline demonstration, version comparison polish and usability pass on English/Hindi examples. Four or five imported videos must remain easy to navigate without a cluttered portfolio dashboard.

The design passes review when a first-time user can answer these without instruction: **What should I inspect first? Which original moment supports this claim? What edit is proposed? Is this a measured result or an assumption? What has not been inspected?** A five-minute usability check should record where users hesitate, misread a percentage or miss a coverage warning. Fix those points before adding animations or more analytics cards.
