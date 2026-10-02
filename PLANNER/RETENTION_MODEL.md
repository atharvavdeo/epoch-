# Risk, drop-off and retention — exact prototype semantics

Authority: formulas and product labels in this file. Formula version `scenario-survival-v1`. All constants below are **design assumptions**, not fitted coefficients or literature estimates. No actual audience data has been used to select them.

## 1. Three different quantities

1. **Diagnostic risk:** severity of evidence-backed editable problems in a time interval. It is an ordinal heuristic on a 0–100 display scale, not the probability a viewer leaves.
2. **Estimated retention scenario:** a first-pass survival curve calculated from explicit baseline assumptions plus risk. It answers “what would this curve look like under these assumptions?” It does not estimate rewatch behaviour.
3. **Observed audience metric:** separately imported authentic data, if available, retaining its definition. YouTube `audienceWatchRatio` can exceed one and need not decrease because sections can be rewatched; it is not identical to first-pass survival. Public most-replayed heatmaps are a fourth, different signal. [S17–S19 in RESEARCH]

The website must show both a risk tab and retention tab. Default retention header: **Estimated retention — uncalibrated scenario**. Subtext: “Uses assumed audience behaviour. Percentages and edit differences are not measured predictions.” Keep this text beside the graph and exported metrics, not hidden in an info modal.

## 2. Bins, track risk and missing evidence

Use 5,000ms bins over the full duration; final bin may be shorter. Preserve precise issue/evidence intervals separately. Let an accepted issue severity be low=1/3, medium=2/3, high=1. Evidence weight is supported=1, provisional=0.5; unknown contributes no known score and marks missing evidence where applicable. These weights rank certainty heuristically, not probabilistically.

For each issue j and bin b, contribution = severity × evidence weight × fraction of bin overlapped by its affected interval. Deduplicate same cause_group_id by maximum contribution. Track risk r[k,b] is the maximum cause contribution in that track; it is zero only when that track was sufficiently inspected and no accepted cause is found. Taking a maximum avoids adding many correlated symptoms into a fake high-confidence penalty. Persist all contributing IDs so the user can inspect what dominates.

Tracks/weights: narrative .30, visual .25, pacing .20, text .15, technical .10. A signal or issue is assigned exactly one risk track; modality labels are orthogonal. Feature availability maps as follows: narrative requires valid transcript+narrative stage; visual requires valid sampled VLM coverage; pacing requires audio/VAD plus transcript and shot signals where relevant; text requires OCR inspection (no detected text is a valid observed result); technical requires decode/visual and waveform technical checks. Missing audio makes audio-dependent portions unavailable, not clean.

For each track and bin store observed fraction c[k,b] in [0,1] according to declared sampling/stage coverage. Coverage describes inspected windows, not a guarantee every event was observed. With known track risk r, lower bound l[k,b]=c×r and upper bound u[k,b]=c×r+(1-c). If wholly unknown, use [0,1]. Combined lower L[b]=sum(weight×l); upper U[b]=sum(weight×u). Evidence coverage C[b]=sum(weight×c). Point risk exists only when C[b]=1; otherwise show an interval/hatched unknown, not an averaged healthy score. Display 100×risk, rounded to integer, labelled heuristic.

Script-only mode uses a separate `script-only-v1` profile: narrative weight .75 and estimated pacing .25, all other tracks not applicable. It cannot be directly ranked against multimodal risk. User-supplied timing or estimated script timing is labelled; no visual/audio quality claim. Estimated pacing cannot establish actual spoken delivery faults.

## 3. Baseline assumptions

Default hypothetical baseline anchors for videos ≥60s: B(0)=1, B(30s)=0.80, B(T)=0.45. Chosen only because they give an interpretable visible scenario; **they are not “typical YouTube retention.”** User may change `retention_at_30s` and `retention_at_end` with 0<end≤at30≤1. For ≥60s hypothetical outputs, use piecewise constant baseline hazard:

- for 0≤t<30: h0 = −ln(at30)/30;
- for 30≤t≤T: h0 = −ln(end/at30)/(T−30).

The controls must require explicit acknowledgement “These are assumptions” before displaying central percentage summary cards on first use. The risk chart remains immediately available. If assumptions are not acknowledged, retention graph may be a clearly watermarked preview, with summary cards blank. Persist acknowledgement with assumptions and project, not globally for every project.

## 4. Risk-adjusted scenario

Let κ=1.0 by default. Additional hazard at time t is `(κ/T) × r(t)`. Thus h(t)=h0(t)+(κ/T)r(t). Integration uses seconds, splits bins at 30s, and preserves short final-bin duration. For interval Δt with constant h, S(end)=S(start)×exp(−hΔt), starting S(0)=1.

With partial coverage, calculate two curves: lower survival using U[b], upper survival using L[b]. Do not fill missing risk with zero to generate a single preferred curve. Central curve and summary are available only if all scored bins have complete required-track coverage. Complete sampled coverage still carries a sampling-limitation label. Additional sensitivity curves using κ=0.5 and 1.5 may be shown separately; they are assumption sensitivity, not statistical confidence bands. Keep the assumed-baseline curve B(t) available as a dashed reference.

Conditional drop in a bin = 1−exp(−hΔt). Absolute audience-share drop = S(start)−S(end). Display conditional drop as “scenario loss among viewers still watching” and absolute drop in percentage points. Neither is a classifier probability. Highest **editable-risk** intervals are ranked by issues, not merely by earliest absolute curve decline. Return top five nonoverlapping regions by max risk × duration, merging adjacent flagged bins of the same dominant cause; maintain trace to underlying issues.

AVD scenario = integral S(t)dt. For constant hazard interval, contribution is S(start)×(1−exp(−hΔt))/h; if h=0, S(start)×Δt. APV scenario =100×AVD/T. End retention =100×S(T). Use exact integration, not a mean of sparse displayed chart points. Partial coverage yields metric ranges, never an unlabeled point estimate. Show duration with every comparison.

## 5. Suggested edits and improvement

P1 shows expected *mechanism*: “removes 3.2 seconds of nonspeech”, “brings first payoff 42 seconds earlier”, “replaces repeated claim with a concrete example.” Only measured duration/position changes can be numerical without a scenario. No LLM-generated “+18% retention” is accepted.

P2 has two modes:

- **Hypothetical edit scenario:** source timeline transformed by validated cuts; carried risk mapped to retained spans; baseline anchors/κ are kept equal across the comparison but T is recomputed. Explicitly assumed resolution of an issue is listed individually. Rewrites/moves/insertions ordinarily require reanalysis; there is no automatic zero-risk replacement. A user can explore an explicit “if this concern were resolved” assumption, which is stored separately from issue review status.
- **Reanalysed upload:** externally edited video receives a new full run. Compare diagnostic evidence and the same assumption profile, without claiming actual viewer uplift. Changed title/promise is separately identified so a better score is not attributed only to editing.

Report APV difference in percentage points, AVD difference in seconds, duration change and issue/coverage change together. Shorter videos can mechanically increase APV while reducing total watched seconds; no winner badge based on APV alone. A move may introduce missing prerequisites; until checked, numeric uplift is suppressed. Baseline/input/model changes make comparison `not_comparable` with reason until harmonised or explicitly shown side by side.

## 6. Validation and later calibration

Formula unit tests establish implementation correctness only. Human labelled defects can validate localisation/usefulness of issues, not viewer retention probabilities. With authentic matched audience data, first decide the metric to model: YouTube watch ratio requires accounting for replays; a monotone survival formula should not be presented as a full model of that ratio. Add a separate empirical model/formula version if needed, trained on video-level splits and evaluated on unseen creators/videos. Never calibrate on four demo videos and claim generalisation.

No actual rate accuracy, causal uplift or statistically calibrated confidence interval is a P1–P3 deliverable without the required labels. The PS validation requirement is **partially met** by diagnostic evaluation; actual audience-curve validation remains a clearly recorded gap. vRetention may support a separate replay-interest experiment, not this gap's closure.

## 7. Golden fixtures for implementation

- Zero risk, full coverage, T=600: S(30)=0.80 and S(600)=0.45 within 1e−6 before display rounding.
- Uniform risk1, κ1, T600: S(600)=0.45×exp(−1), about16.55%; this demonstrates the chosen penalty, not a measured outcome.
- Unknown visual track all video: risk upper−lower includes .25; no central curve/point summary.
- All risk0 and at30=end=1: AVD=T, APV100; h=0 branch safe.
- One issue spanning2.5s of a5s bin contributes half its weighted severity.
- Two same-cause duplicate findings cannot raise track risk above the stronger one.
- A601s video has120 full5s bins and one1s bin; integral uses actual duration.
- A dismissed issue remains in baseline evidence; only an explicit scenario configuration changes inclusion.
