# Prediction contract — text-retention-v3

Endpoint: `GET /api/v1/runs/{run_id}/prediction` (and `POST` to recompute with new assumptions).
Producer: `pipeline/predict/` (stage `predict`, version 6). Converter: `pipeline/predict/view.py`.

Two outputs, never mixed up:

1. **Heuristic transcript risk** (`risk_bins`, `findings`): traceable to rules and quoted passages. 0–100 ordinal score, **not a probability of leaving**.
2. **Retention scenario** (`per_second`, `summary`, `drop_moments`): a curve from those rules plus explicit audience assumptions. `calibrated: false`, always labelled uncalibrated.

All v2 fields are still present. v2 packages are upgraded on read (baseline reported as `piecewise_constant_v2`, cumulative watch time and risk bins derived from stored data).

## Storage note

The package schema (`contracts/entities.py`, `extra="forbid"`) does not allow new top-level, per-second or drop-moment keys, so `prediction.json` stores the v3 additions inside `analysis` (`analysis.risk_bins`, `analysis.findings`, `analysis.baseline`, `analysis.risk_weights`, `analysis.scenario_series`, `analysis.drop_moment_headlines`) and `summary` (`watch_time`, `assumptions`, `timing_source`). The API response is flat, as below. Read the API, not the file.

## Top-level response fields

| field | type | meaning |
|---|---|---|
| `model_version` | `"text-retention-v3"` | |
| `label`, `calibrated`, `band_label` | str, `false`, str | show beside every chart |
| `anchors` | `{retention_at_30s, retention_at_end}` | assumed neutral video |
| `baseline` | object | see below |
| `per_second[]` | list | scenario curve, one bin per second (last bin may be fractional) |
| `summary` | object | metrics, see below |
| `drop_moments[]` | list | top scenario-loss windows, with plain headlines |
| `risk_bins[]` | list | 5-second heuristic transcript risk |
| `findings[]` | list | ranked reviewable findings |
| `risk_weights` | object | every policy weight with a one-line rationale |
| `weights` | object | per-feature log-hazard priors (`weight`, `reason`, `rationale`, `group`) |
| `analysis` | object | v2 block (findings, risk_bins, promise_ledger, coverage, ...) kept for the old UI |
| `feature_info.sources[]` | list of str | which inputs were used; absent inputs say `"no …: … off"` |
| `notes[]` | list of str | honesty notes |
| `recomputed` | bool | POST only |

## per_second[i]

v2 fields: `t, end_s, duration_s, retention, lower, upper, neutral, hazard_per_s, baseline_hazard_per_s, conditional_loss, loss, excess_loss, contributions{feature: share}, protective[], risk_groups{group: 0..1}, transcript_risk`.

New: `cumulative_watch_s` (∫S dt from 0 to `end_s`, seconds), `neutral_cumulative_watch_s` (same for the neutral video).
`transcript_risk` / `risk_groups` now equal the 5-second risk bin that contains the second.
`lower`/`upper` = **assumption sensitivity** (all weights ×0.5 / ×1.5), not a confidence interval.

## summary

v2: `duration_s, avd_s{central,lower,upper}, apv_pct{…}, end_pct{…}, neutral_avd_s, neutral_end_pct, excess_loss_by_feature`.
New: `watch_time {avd_s, neutral_avd_s, duration_s, apv_pct, delta_vs_neutral_s}`, `assumptions {anchors, baseline{kind, shape_k, end_drop_multiplier, end_drop_fraction}, band, calibrated}`, `timing_source` (`aligned_words` | `segment_timestamps`).

## baseline

`{kind, shape_k, end_drop_multiplier, end_drop_fraction, anchors, scale_after_30s, formula, description}`

- `kind`: `weibull_two_segment` (default), `piecewise_constant` (shape_k = 1), `piecewise_constant_v2` (old package).
- Opening 0–30 s: `H0(t) = −ln(a)·(t/30)^k`. After 30 s: `H0(t) = H0(30) + λ·W(t)`, `W(t) = ∫₃₀ᵗ m(s) d(sᵏ)`, `m = end_drop_multiplier` in the last `end_drop_fraction` of the video. λ is solved in closed form so a feature-free video hits `S(30)=a` and `S(T)=z` exactly. Videos ≤ 30 s use one segment from 0.
- Defaults: `shape_k 0.6` (hazard falls over time, so the curve bends), `end_drop_multiplier 1.5`, `end_drop_fraction 0.05`. `shape_k 1, multiplier 1` reproduces v2.

## risk_bins[j]

`{start_s, end_s, risk (0–100 float), groups {opening_promise, progress, comprehension, questions_payoff, interruptions, delivery, visual_pacing: 0..1}, top_finding_id | null, finding_ids[]}` plus the v2 keys `start_ms, end_ms, duration_s, score (= risk), label`.

`risk_b = 100 · Σ_c α_c · max_{j∈c} s_j·e_j·o_{j,b}`. s = severity (low ⅓, medium ⅔, high 1), e = evidence (supported 1, provisional 0.5), o = share of the bin the finding covers. Taking the max inside a group means two symptoms of one cause never add up. Label it **heuristic transcript risk**. Realistic values are small (a bin with one low, provisional finding is about 2–4); do not rescale it to look like a probability.

## findings[k] (sorted by `priority_rank`)

| field | notes |
|---|---|
| `finding_id`, `rule_id` (snake_case, e.g. `repetition`), `rule_code` (`A1`…`E4`, `V1`…`V6`, `C5`, `S1`), `rule_family` | |
| `cause_group`, `group_label` | plain group name |
| `title` | short creator headline, e.g. "Long setup before the first point" |
| `start_ms`, `end_ms` | |
| `status` | `candidate` (never auto-accepted) |
| `severity` | `low` / `medium` / `high` |
| `evidence_strength` | `supported` (direct measurement) / `provisional` (narrative extraction or lexical matching) |
| `quote`, `source_segment_ids` | |
| `earlier_quote`, `earlier_start_ms`, `earlier_end_ms` | repetition / recap / stacked questions |
| `later_answer_candidates[]` | questions, term definitions |
| `measurements` | numbers and the detector description |
| `mechanism` | plain-language why (one or two sentences) |
| `counter_explanation`, `suggestion`, `preserve` | |
| `safe_edit`, `edit_kind` (`trim`, `move`, `rewrite`, `insert`, `confirm`, `review`, `audio_fix`) | |
| `needs_reanalysis` (= `requires_reanalysis`) | true for anything except trims and audio fixes |
| `scenario_feature`, `scored_in_scenario` | whether the rule also moves the retention curve |
| `priority_score` (0–100), `priority_rank`, `priority_components`, `duplicate_of` | editorial value, not curve drop |

Rule families → groups: **A** opening/promise (A1 long preamble > 15 s after hook, A2 no hook identified, A3 delayed title payoff (> 45 s and > 20 % of duration), A4 unconfirmed promise). **B** progress (B1 repetition, B2 low novelty, B3 topic drift with no link back). **C** comprehension (C1 sentence > 30 words, C2 term before explanation, C3 dense new terms, C4 abstraction ≥ 40 s, C5 dense on-screen text during fast speech). **D** questions/payoff (D1 question without timely callback, D2 new questions while earlier ones are open). **E** interruptions (E1 CTA before first payoff, E2 sponsor/mid-video CTA, E3 extended outro, E4 redundant recap). **V** delivery (V1 slow, V2 fast, V3 fillers, V4 dead air, V5 flatter/quieter delivery, V6 loudness drop). **S** visual pacing (S1 long low-motion shot).

Priority = 100 × (0.30 evidence + 0.25 severity + 0.15 safe edit + 0.10 duration (saturates at 30 s) + 0.10 title relevance + 0.10 misunderstanding risk), × 0.5 when it mostly overlaps a higher-priority finding of the same group.

## drop_moments[m]

v2: `start_s, end_s, excess_loss, retention_before, retention_after, reasons[{feature, share, text}], quote, issue_ids, finding_ids`.
New: `headline` (plain sentence: what happens there and why, from the matching finding or the top reason), `headline_finding_id` (when a finding supplied it). `finding_ids` are sorted by priority.

## POST body

`{retention_at_30s (0,1], retention_at_end (0,1], acknowledged: true, shape_k? [0.3,1.0], end_drop_multiplier? [1,3], end_drop_fraction? [0,0.2]}`. Out of range → 422; `acknowledged: false` → 409. Findings and risk bins do not change on recompute (they do not depend on audience assumptions).

## Measured optional signals (all off when the input is missing)

| feature | group | weight | input |
|---|---|---|---|
| `long_static_shot` | visual_pacing | +0.4 | shots: length > max(8 s, 3× median shot) and motion in the lowest quarter |
| `fresh_visual_change` | protective | −0.15 (cap −0.1) | shot cuts |
| `new_onscreen_text` | protective | −0.15 (cap −0.1) | OCR tracks (confidence ≥ 0.5, not present from the first frame) |
| `dense_text_fast_speech` | comprehension | +0.3 | OCR ≥ 12 words on screen while local speech > 1.1× speaker median |
| `loudness_drop` | delivery | +0.4 | short-term LUFS ≥ 10 LU below trailing 10 s speech median for ≥ 3 s, VAD speech present |
| `energy_lift` | protective | −0.1 | short-term LUFS ≥ 4 LU above speaker median for ≥ 3 s |
| `flat_low_energy` | delivery | +0.2 | 10 s pitch windows: pitch std < 0.6× median and loudness > 3 LU below median, ≥ 2 windows |

At most one protective signal counts per second, capped at −0.1, and only when no risk group is active. Pitch and loudness describe delivery relative to the same speaker; never call them emotion.
