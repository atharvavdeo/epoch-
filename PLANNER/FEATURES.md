# Feature catalogue and detection contracts

The user's original 64 signals are all accounted for below. **P1** = required foundation; **P2** = required extension unless explicitly marked optional; **P3** = evaluation; **B** = backlog, no current build promise. “Measure” is an observation, not an automatic retention penalty. Feature IDs F01–F64 correspond to the user's numbering.

| ID | Signal | Delivery / how | Limit and reason |
|---|---|---|---|
| F01 | Hard cuts | P1: PySceneDetect AdaptiveDetector; frame-level PTS boundaries, cuts/10s. | Camera flashes/movement may trigger false cuts; preserve candidate score. |
| F02 | Dissolve/fade/wipe | P2: fades from luminance trends; VLM tags sampled transition candidates. Wipe classifier B. | Report `soft_transition_unknown` unless visually supported; no exact universal taxonomy. |
| F03 | Jump cuts | P2: candidate same-scene appearance + discontinuity, contextual VLM check. | Camera motion confounds; provisional when boundary frames insufficient. |
| F04 | Shot length | P1: differences between cut boundaries; mean/max/std. | No rule that long shot means boring. |
| F05 | Scene vs shot | P2: group shots by transcript topic and visual descriptions. | Semantic scenes have approximate boundaries; retain original shots. |
| F06 | Black/blank | P1: FFmpeg blackdetect, duration and frames. | Intentional fades excluded from fault flags after context review. |
| F07 | Freeze/static | P1: freezedetect + frame-change measurement, distinguish decode repeat from intentional slide. | Useful diagrams are not penalised merely for low motion. |
| F08 | Zoom/punch-in | P2 optional: optical-flow expansion + visual review. | Numerical optical flow is not reliable cinematic intent; avoid mandatory dependency. |
| F09 | Pan/tilt | B: global flow decomposition. | Lower priority than grounded retention issues. |
| F10 | Camera shake | P2 optional: unstable global motion candidate. | Handheld style may be intentional; no clinical discomfort claims. |
| F11 | Motion energy | P1: robust frame differences on downscaled frames. | Camera movement, cuts and content motion separated where possible. |
| F12 | Speed ramp/slow-mo | B: difficult without source frame-rate/semantic evidence. | Do not infer playback-speed changes from motion alone. |
| F13 | Angle/shot type | P2: coarse VLM labels wide/medium/close/screen/unknown. | Sampled labels, no exact continuous framing guarantee. |
| F14 | Captions | P1 OCR tracks; P2 caption-speech correspondence and observed coverage. | OCR visibility coverage ≠ complete subtitle coverage; burned-in only. |
| F15 | Title cards/callouts | P1 OCR boxes/content; P2 role classification. | Keep OCR confidence separate from semantic certainty. |
| F16 | Lower thirds | P2: persistent text location + visual role. | Name recognition not required. |
| F17 | Stickers/emojis/GIFs | B; may appear in general VLM descriptions. | No reliable object inventory or counts promised. |
| F18 | Arrows/highlights | P2: coarse presence/relevance in inspected frames. | Counts limited to sampled observations. |
| F19 | PIP/split screen | P2: VLM layout labels with frame evidence. | Multiple regions do not imply clutter. |
| F20 | Progress/chapters | P2: OCR/VLM structural cue. | Presence supports structure; absence is not a defect. |
| F21 | Watermark/logo | P2: persistent overlay observation. | No brand recognition requirement or penalty for branding alone. |
| F22 | Text density | P1 OCR word count/area; P2 reading-time proxy from tracked text dwell. | Hindi tokenisation and OCR errors disclosed; avoid words/sec from one frame. |
| F23 | Brightness | P1 luminance distribution and clipping fraction. | Dark style may be intended; technical fault needs context. |
| F24 | Colour/saturation | P1 inexpensive diagnostic statistics. | Analytics only; no direct saturation→retention penalty. |
| F25 | Colour jump | P2: adjacent-shot luminance/colour shift candidate. | Lighting/location changes can be valid. |
| F26 | Blur | P1 Laplacian/edge proxy on source crops; visual confirmation for issue. | Threshold is resolution/content dependent; no universal quality score. |
| F27 | General VQA | B: trained perceptual quality model. | Existing measurements cannot be relabelled calibrated VQA. |
| F28 | Saliency/eye attention | B. | Saliency is not measured human gaze; avoid speculative attention maps. |
| F29 | Clutter | P2: described competing text/regions, grounded examples. | Subjective; actionable claim requires actual obstruction/conflict. |
| F30 | Face present | P2: coarse VLM presence at sampled frames. | No identity recognition; temporal coverage approximate. |
| F31 | Face size | B: dedicated box detector if later useful. | VLM estimate not numeric face area truth. |
| F32 | Eye contact | B. | Lens geometry/pose uncertainty too high for retention penalty. |
| F33 | Expression/emotion | B as scoring; optional visible-expression description only. | Do not infer boredom, sincerity, confidence or mental state. |
| F34 | Gestures | B quantitative; coarse observed movement may be described. | Sparse frames miss gestures. |
| F35 | Person count | P2 coarse sampled count/unknown. | No continuous tracking or identity requirement. |
| F36 | A-roll/B-roll | P1 coarse clip labels with VLM; P2 sequence analytics. | B-roll relevance matters more than ratio; unknown preserved. |
| F37 | Screen recording | P1 coarse clip label. | Long screen tutorials can retain information despite few cuts. |
| F38 | Speech presence | P1 Silero VAD through ASR; intervals and fraction. | Music/overlap can confuse VAD; preserve confidence/unknown. |
| F39 | Silence | P1 waveform silence + VAD pauses; interval union. | Pause includes possible intentional emphasis or visual demonstration. |
| F40 | Speech rate | P1 word count over aligned speech windows. | Code mixing/tokenisation affect WPM; provisional if word timing absent. |
| F41 | Loudness/energy | P1 FFmpeg loudness/peak plus windowed RMS. | Low loudness ≠ low engagement; flag abrupt or intelligibility concerns. |
| F42 | Pitch variation | P2 optional librosa pyin on voiced spans. | Pitch-tracking errors/music; analytics only, no “monotone = bad” rule. |
| F43 | Background music | B reliable separation/classification. | VLM cannot hear video frames; do not invent music observations. |
| F44 | Sound effects | B acoustic event model. | Amplitude spike alone cannot identify whoosh/ding. |
| F45 | Beat sync | B: beat estimator + cut alignment. | No need to optimise music-video structure for two initial categories. |
| F46 | Audio quality | P1 clipping/peak discontinuities; P2 noise proxy contextual review. | Noise measurement requires suitable nonspeech spans; otherwise unknown. |
| F47 | Language switches | P1 ASR chunk hints + text analysis; mixed/unknown allowed. | Not every borrowed English term is a language transition. |
| F48 | Hook | P1 Cerebras extracts concrete opening promise/question and evidence span. | No forced five-second hook rule. |
| F49 | Title payoff | P1 title obligations → partial/concrete fulfilment intervals. | Preview ≠ fulfilled promise; multiple title promises kept separately. |
| F50 | Repetition | P1 multilingual embeddings retrieve nonadjacent pairs; LLM distinguishes recap/elaboration. | Similarity is retrieval, not probability; cite both ranges. |
| F51 | Tangent | P1 chapter/topic relation + LLM contextual judgement. | Setup needed for later explanation can be justified. |
| F52 | Fillers | P1 language-aware candidate lexicon + contextual check. | Hindi “toh” and “matlab” often carry meaning; no blanket deletion. |
| F53 | Viewer questions | P1 rhetorical/direct question spans. | Presence is analytic, not automatic retention gain. |
| F54 | Open loops | P1 tease/promise → resolved/unresolved/uncertain links. | Topic closure can be implied; avoid invented unresolved claims. |
| F55 | CTA/sponsor | P1 transcript spans; placement/duration. | Sponsor classification tentative unless stated; contractual edits require creator review. |
| F56 | Information density | P2 candidate claims/concepts per span + supporting examples. | Heuristic, not count of universally new information. |
| F57 | Sentiment/energy words | B score; source wording available to reasoning. | Enthusiastic language does not establish usefulness or retention. |
| F58 | Cold open | P1 structural transcript + VLM context. | Difference between teaser and explanation matters. |
| F59 | Greeting/intro | P1 classify intro span and time to substantive delivery. | Greeting itself is not necessarily a defect. |
| F60 | Logo sting | P2 combined visual persistent branding + low information interval. | Intentional brand identity may be retained. |
| F61 | Chapters | P1 paragraph/topic segmentation with bounded boundaries. | Chapters are inferred, editable annotations, not original creator metadata. |
| F62 | Sponsor section | P1 linked F55 intervals, separately addressable. | No duplicate penalty when CTA/sponsor tags overlap. |
| F63 | Recap | P1 narrative role used to suppress repetition false positives. | Recap length still reviewable when disproportionate. |
| F64 | Outro | P1 closing/CTA spans; P2 visual end-card observation. | No cut recommendation that removes essential conclusion. |

## Additional feature requirements

| ID | Feature / phase | Implementation and reason |
|---|---|---|
| X01 | Evidence coverage P1 | Modality/time masks and sampling gaps distinguish unobserved from inspected-clear. |
| X02 | Promise ledger P1 | Title obligations, setup, partial delivery and fulfilment prevent a keyword mention being mistaken for payoff. |
| X03 | Modality agreement P2 | Match spoken claim/entity to visual descriptions/OCR; flag specific contradictory or unsupported visual accompaniment. Descriptive grounding, not fact-checking all world claims. |
| X04 | Useful static visual P1 | Suppress stagnation defect when diagram/demo changes information through explanation. Human-readable counter-evidence required. |
| X05 | Text dwell/occlusion P2 | OCR track duration/position, competing text and visible obstruction; identify unreadable callout with frame references. |
| X06 | Prerequisite continuity P2 | Proposed move/cut checked against referenced entities and preceding definitions; unresolved dependency means needs_reanalysis. |
| X07 | Intro payoff timeline P1 | Visualise opening promise, first substance and fulfilment as separate markers. |
| X08 | Risk + retention P1 | Exact deterministic aggregation/scenario in RETENTION_MODEL, independent of LLM invented scores. |
| X09 | Why not a problem P1 | Store counter-explanations and dismissed candidates; avoid one-sided alarming critique. |
| X10 | Action plan / before-after P2 | Non-destructive edits and two clearly separated hypothetical/reanalysed comparisons. |
| X11 | Grounded chat P2 | Answer only from current run evidence; link timestamps; propose rerun when frame coverage is insufficient. |
| X12 | Resumable package loop P1/P2 | P1 stage checkpoints; P2 local request/export/import UI with lineage. |
| X13 | Evaluation and provenance P3 | Human defect labels, source citations, measurements, authentic metric overlay if available. |

## Initial issue ontology

Allowed issue types: `delayed_payoff`, `slow_intro`, `unnecessary_repetition`, `tangent`, `unresolved_promise`, `dead_air`, `rushed_delivery`, `visual_stagnation`, `visual_speech_mismatch`, `unreadable_text`, `visual_overload`, `technical_visual_fault`, `technical_audio_fault`, `disruptive_cta`, `weak_transition`.

P1 uses all except visual_speech_mismatch, unreadable_text as a dwell judgement, visual_overload and weak_transition; those contextual types enter P2. P1 may surface an OCR-small-text candidate as provisional technical_visual_fault only with frame evidence. The ontology is intentionally much smaller than the measurement catalogue. Measurements do not independently become dozens of warnings.

## Candidate thresholds and adjudication

Initial candidate retrieval defaults (engineering priors, tune only on development clips): shot ≥15s with low frame change; nonspeech pause ≥2s outside identified demo/music-only content; transcript repetition top three nonadjacent neighbours with cosine ≥0.85; greeting/substance delay ≥20s; OCR text dwell below `max(1s, words/3)`; clipped-sample fraction ≥0.1% within a one-second waveform window. Each is a review trigger, not an issue verdict. Frame-change/blur thresholds are relative to a video's distribution until annotated examples justify fixed values. Record actual configuration and raw measurements.

Run a fixed evidence-adjudication pass: candidate → retrieve context (previous/current/next narrative span and bounded frames) → identify an editorial mechanism and counter-explanation → accept supported/provisional or dismiss → deduplicate overlapping same-cause findings. A delay issue's affected interval covers the waiting period, while its payoff evidence may sit later. Display both. Distinct simultaneous causes may remain separate, but aggregation caps duplicate penalties as specified in RETENTION_MODEL.

## Script-specific ideas from the original proposal

The original script notes are editorial candidates, not universal prohibitions. They map into the existing ontology rather than inventing extra risk scores:

| Proposal | Planned treatment | Reason |
|---|---|---|
| Weak bridging, sudden technicality/context jump | P2 weak_transition + prerequisite review, cite both adjoining spans | A transition can be clear without an explicit connecting word. |
| Slow delivery, wasted hook, extensive history/unboxing before substance | P1 slow_intro/delayed_payoff/tangent with title and genre context | Unboxing/history may itself be the promised topic. |
| Overexplaining and spec-sheet dumping | P2 information-density/example support; suggest a relevant practical implication | A technical audience may need exact numbers; never invent product performance to make a rewrite punchier. |
| Monotonous structure / uninterrupted monologue | P2 structural variation analytics with contextual issue adjudication | Long explanation can be valuable; rhetorical questions/cuts are not mandatory. |
| Announcing the ending / siloed chapters | P1 outro/chapters analytics, P2 transition suggestion when content actually loses continuity | Do not claim chapter navigation causes abandonment or hide useful structure to trap viewers. |
| Neutrality boredom / buried dealbreakers | P1 promise/claim coverage, P2 specificity and placement suggestions | Do not force controversy or distort balanced conclusions; only reorder concerns present in source. |
| Real-world dilemma hook | P1 concrete alternative hook based on source facts and intended audience | Proposed wording must preserve factual support and avoid invented sensational claims. |
| Replace “and” with “but/therefore” | Optional rewrite when actual causal/contrast relation exists | No lexical ban; inserting causal language without causation misrepresents the content. |
