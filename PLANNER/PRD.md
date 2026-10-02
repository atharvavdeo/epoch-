# Product requirements — PS5 Retention Predictor

## 1. Overview

A creator uploads a script or supplies a video for offline analysis and sees **where attention may be lost, what evidence supports that concern, and what edit could address it**. The primary output is a synchronised review workspace: playable video, transcript, risk tracks, estimated retention scenario, issue evidence and an edit plan.

The analysis separates speech/narrative problems from visual problems before combining them. A long uncut shot is a measurement, not inherently a defect. A model must account for what the speaker explains and what changes on screen. All semantic findings cite bounded evidence; deterministic validators control accepted intervals, artifact references and downstream actions.

AI build summary: a Python Colab batch pipeline exports a versioned ZIP; a local FastAPI service validates/imports it into SQLite/files; a React website renders it and calls a server-side Cerebras adapter for grounded language tasks. Video perception occurs in Colab, not through the website. No model training is required for the initial product.

## 2. Goals, success criteria and anti-goals

G1: pinpoint actionable intervals with separate speech/visual/audio/text evidence. G2: make the PS's retention/drop-off requirement visible and intelligible without presenting assumed rates as observed. G3: support repeated uploads and selective reanalysis without repeatedly downloading/loading weights. G4: demonstrate 4–5 videos across English, Hindi/Hinglish, tech reviews and education. G5: allow a builder to reproduce outputs from frozen inputs, prompts, model revisions and environment locks.

Phase success is defined in §13 and VALIDATION. Primary product metrics are evidence validity, timestamp localisation, issue usefulness, coverage, runtime and repeatability. Audience retention accuracy remains unmeasured until genuine matching labels are available. Anti-goals and negative scope have their single authoritative home in §3.

## 3. Scope, phases and boundaries

| Phase | What it is / end goal | What it is not / excluded in that phase | Exit gate |
|---|---|---|---|
| P1 Diagnose | End-to-end import/review of one real 5–15 minute video; English/Hindi transcript; cuts/pause/OCR primitives; bounded VLM observations; narrative findings; per-track risk; assumed retention scenario; evidence cards and static edit suggestions. Script-only path is explicitly provisional. | No automatic media editing, chat tools that rerun Colab, model fine-tuning, live video streaming, or polished animation. No factual prediction of actual viewer percentages. | A complete valid package plays correctly; a partial package clearly marks missing stages; no fabricated evidence; all P1 requirements pass. |
| P2 Improve | Add contextual visual/text/audio checks, project chat, review/dismissal, staged cut/move/rewrite plans, hypothetical comparison, rerun request export, edited-video reupload and lineage. | No remote Colab control, video rendering, voice cloning/TTS, automatic stock-footage purchase, or autonomous edits. Scenario improvements are not causal results. | An issue can be inspected, turned into a plan, compared, reanalysed and traced to a new run without overwriting original evidence. |
| P3 Demonstrate and evaluate | Four or five frozen genuine packages, annotation/holdout evaluation, reproducible environment locks, offline resilience, provenance/report export; optional actual-metric overlay. | No production SaaS, auth/billing/team management, broad accuracy claim from a few videos, guaranteed creator uplift, or dependence on unavailable dashboards. | Rehearsed demo works without GPU/network; validation report distinguishes measured diagnostics from retention assumptions. |

Global included scope: 300–900 second videos; tech reviews and education; spoken English/Hindi and common mixed speech; source title supplied by user; local single-user desktop website; manual Colab operation. Vlogs are backlog pending category-specific evaluation. Inputs outside duration/category may be rejected clearly rather than silently analysed under the wrong rules. P1 script-only accepts 200–5,000 words and estimates timing at a user-editable default 140 words/minute; actual recording support still targets 5–15 minutes. This word-rate default is a timeline convenience, not a Hindi fluency norm.

Global excluded scope: YouTube uploading/downloading integration, creator OAuth, audience identity prediction, recommendation algorithm emulation, medical/psychological inference from expressions, emotion-to-retention scoring, automated final video generation, synthetic audio, full NLE, agent orchestration frameworks, mobile app, vector database, distributed workers, cloud GPU serving, billing and collaborative editing. Ordinary local metadata export is included; formatted PDF/DOCX export is backlog.

## 4. Jobs to be done

Before publishing, locate the first concrete delivery of the title promise. Identify unnecessary delays and repeated material while preserving pedagogical recap. Check whether visuals support the spoken point and whether text can reasonably be read. Separate technical faults from editorial preferences. Prioritise a small set of worthwhile edits and inspect the evidence before applying them externally. Reanalyse a changed cut without confusing old and new timelines.

## 5. User stories and requirements

| ID | Story / required behaviour | Phase |
|---|---|---|
| US01 | As a creator, register title, category, language and script/video; import an analysis package; see whether results are complete, partial or stale. | P1 |
| US02 | As an editor, click a finding and see the exact source interval, transcript quote, frame references, measured signals and uncertainty. | P1 |
| US03 | As a creator, inspect separate modality risk tracks and the estimated retention curve with its assumptions, coverage and highest-risk regions. | P1 |
| US04 | As an editor, obtain concrete cuts/moves/rewrites, stage changes, see conflicts and compare an explicitly hypothetical scenario. | P1 suggestions; P2 plan/comparison |
| US05 | As a creator, ask questions in English/Hindi about this video and receive evidence-linked answers, or a precise statement of missing evidence. | P2 |
| US06 | As an operator, resume interrupted Colab stages, export rerun requests and import new run revisions or externally edited media without overwriting history. | P1 resume; P2 UI rerun/versioning |
| US07 | As a judge, explore 4–5 actual analyses and measured diagnostic evaluation, with honest retention-data limitations and an offline path. | P3 |
| US08 | As an operator, optionally overlay genuine retention data with explicit metric semantics, source and alignment. | P3 conditional |

R01 US01: accept MP4/MOV/MKV for Colab decode, produce browser-compatible proxy; local website accepts validated ZIP and optional matching local media. R02 US01: show processing origin, run date, hardware/model/profile and stage coverage. R03 US02: every accepted issue has at least one valid evidence ID, a bounded interval, cause, severity, evidence status, counter-explanation and specific suggested action. R04 US02: show speech, visual, audio and on-screen-text tags independently; combined findings retain all contributing evidence. R05 US03: retention and risk follow RETENTION_MODEL exactly, with visible uncalibrated labels. R06 US03: missing analysis is displayed as unknown, never zero risk. R07 US04: suggestions quote actual words when referring to speech; move suggestions specify destination; insertions contain proposed wording and distinguish it from original content. R08 US04: edit plans do not mutate source media. R09 US05: all factual video claims cite existing evidence; chat cannot create source observations. R10 US06: fingerprints decide cache reuse; reruns are immutable children. R11 US07: provenance and evaluation export contain no secrets. R12 US08: never substitute public replay heatmaps for remaining-viewer data.

## 6. User experience and end-to-end process

**P1:** creator supplies metadata and video to the Colab workflow → operator passes preflight → pipeline measures/transcribes/observes → narrative reasoning produces validated issues → deterministic risk/scenario aggregation → downloadable package → website validates and imports → creator inspects video, timeline and suggestions. The website explains that local video upload alone does not launch GPU analysis. "Prepare analysis" downloads a request file and provides notebook instructions; "Import analysis" accepts the returned ZIP. A script can run through the local text path immediately when Cerebras is configured.

**P2:** creator selects an issue → checks evidence → accepts into an edit plan or dismisses with reason → conflict validator checks time ranges → website calculates an assumption-labelled scenario where supported → creator downloads edit/rerun request → changes the video in an external editor or reruns selected analysis in Colab → imports child package → website compares versions by source lineage. Evidence chat shares the active run, selected time range and accepted/dismissed state. A chat answer can propose an action; a visible button stages it after deterministic validation.

**P3:** operator freezes configuration → runs held-out videos → completes annotations/evaluation → prepares local demo collection → judge opens a video and follows evidence to suggested edit and comparison → report reveals model, coverage and evaluation sample size. If authentic retention data is later supplied, an optional importer verifies source/metric semantics and overlays it separately.

Simple website surfaces: Project library, Review workspace, Edit plan, Evaluation/provenance. Review contains player, timestamped transcript, risk/retention tabs, ranked issue cards and (P2) a collapsible chat pane. Use a shared playhead and interval selection. Highest-priority list initially shows five findings; full list remains available. No decorative dashboard KPIs without units and definitions.

## 7. Visual design

[DesignDecisions](DesignDecisions.md) owns adaptation of the supplied [UI_REFERENCE](UI_REFERENCE.md). UI/UX detailing and animation are deferred. Functional clarity, accessible contrast, Hindi rendering and correct time selection are P1 acceptance requirements.

## 8. Data

[Schema](Schema.md) is authoritative for entities, enum values, packages, intervals, missing data, edit operations and migrations. [RETENTION_MODEL](RETENTION_MODEL.md) owns analytical semantics.

## 9. Interfaces

US01 uses project creation, package import/status, run read and media delivery. US02/03 use evidence/issues/timeline endpoints. US04 uses plan CRUD/validation/scenario. US05 uses grounded chat. US06 uses run lineage and rerun-request export. US07 uses evaluation/report export. US08 uses actual-metric import. Exact HTTP contracts and failure codes are in [TRD](TRD.md). No endpoint can start Colab or claim it has done so.

## 10. State map

Project: empty → awaiting_analysis → ready or partial. An active run may become superseded but remains readable. Import job: queued → validating → committed or rejected; rejection makes no project changes. Pipeline run: planned → running → complete/partial/failed/cancelled; stage states and transitions are in Schema. Edit plan: draft → validated → scenario_ready or needs_reanalysis → exported; a new edited-media run may later link back. Chat: idle → pending → answered/abstained/failed, with one bounded retry policy. On page reload, recover persisted state rather than recreate requests.

## 11. Technical requirements

[TRD](TRD.md) and [COLAB_RUNBOOK](COLAB_RUNBOOK.md) own technology, dependency environments, runtime gates, caps and recovery. Research establishes feasibility candidates; actual Colab fit/speed remains a first-build gate.

## 12. Build structure

[MODULES](MODULES.md) defines the intended repository structure and boundaries. These are future paths, not files generated by this planning task. Start with shared schemas and importer before decorating the UI; complete a vertical slice before adding P2 features.

## 13. Acceptance

| Gate | Acceptance / story |
|---|---|
| A01 | US01: importing the same ZIP twice is idempotent; corrupt or unsupported ZIP is rejected atomically with actionable error. |
| A02 | US02: every displayed factual issue links to source evidence; seeking reaches the referenced interval; provisional timing is visibly distinguished. |
| A03 | US03: chart reproduces golden formula fixtures; assumptions are visible beside the curve; missing tracks cannot appear as healthy. |
| A04 | US04: overlapping cuts are rejected or explicitly merged; out-of-range moves fail; compare mode labels old/new duration and assumption status. |
| A05 | US05: unsupported questions abstain; citations resolve to active run; malicious text in transcript cannot trigger tools or change instructions. |
| A06 | US06: interrupted clip rerun preserves completed hashes; changed model/prompt/frames invalidates dependent artifacts; edited media gets a new asset ID. |
| A07 | US07: four genuine packages covering both languages and both initial categories open offline; diagnostic evaluation includes denominator, split and limitations. |
| A08 | US08: optional real metrics retain their identity and native bins; no synthetic or public replay data is labelled actual retention. |

Performance targets: once imported, local timeline/filter interaction p95 below 200ms on the measured demo laptop; player starts within 3s from local proxy under the demo fixture; local chat timeout 45s; 15-minute analysis budget target ≤90 minutes after cached weights, verified before committing to batch size. These are engineering goals, not research-backed speed claims. Record cold setup/download/load separately.

## 14. Risks and gaps

[RISKS](RISKS.md) lists blockers, fallbacks and rethink triggers. Known gaps: no real audience labels today; untested GPU profile; uncertain Hindi/Hinglish alignment and OCR; capacity fallback may weaken visual grounding; arbitrary scenario priors; sampled frames can miss transient events. None is hidden by an aggregate quality score.

## 15. Rollout

Execute [IMPLEMENTATION_PLAN](IMPLEMENTATION_PLAN.md) gates in order. Freeze P1 after a complete real-video slice. P2 uses measured P1 failures to add only justified checks. P3 freezes analysis before holdout evaluation and judge rehearsal. If time compresses, preserve evidence, retention labels and import reliability; defer optional P2 visual detectors and then chat polish. Never remove validation labels to make the product look complete.
