# Failure register, fallbacks and rethink triggers

Owners below are implementation responsibilities, not separate AI agents. PriorityP0 blocks truthful/usable analysis; P1 blocks a feature; P2 limits scope. No listed fallback may silently alter model identity, precision or evidence coverage.

| ID | Failure / priority | Prevention and observable trigger | Fallback / required rethink | Owner |
|---|---|---|---|---|
| RSK01 |80GB GPU unavailable /P0 primary | Preflight actual allocated hardware before download | Declared9B BF16 on40GB with quality gate; otherwise partial/cached demo. Reconsider hardware access, not endless27B retries. | Runtime |
| RSK02 |Weight load or activation OOM /P0 | Budget weight+tokens+workspace; smoke worst-case input | No repeat same weight load; one reduced clip attempt. Profile changes versioned. | Runtime |
| RSK03 |Dependency conflict /P0 | Isolated environments; published metadata/locks | One researched lock revision; unresolved stops gate. Never global upgrades. | Runtime |
| RSK04 |Reference DeltaNet slow /P1 | Warm throughput probe before batch | Separate vetted optimized-kernel experiment or profile change; no demo-time source compilation. | Runtime |
| RSK05 |Drive/runtime loss /P0 | Atomic local writes and verified persistent checkpoints | Resume matching units; disclose lost work since last checkpoint. | Pipeline |
| RSK06 |Hindi/code-mixed ASR wrong /P0 evidence | Inspect representative transcript; separate CER/WER/timing | Correct transcript manually, segment timing fallback; invalidate downstream. Do not invent precise words. | Speech |
| RSK07 |OCR misses tiny/fast text /P1 | Original crops and sampled-coverage flags | Targeted high-resolution refinement; abstain if unsampled. More frames only within runbook cap. | Vision |
| RSK08 |VLM hallucinated event /P0 | Evidence IDs, timestamp caps, actual-image probe | Reject/repair once; unknown region; refine if budget permits. | Reasoning |
| RSK09 |Useful static/recap flagged /P1 | Context/counter-explanation; negative controls | Adjust development rubric and suppress unsupported issue type; preserve raw measurement. | Evaluation |
| RSK10 |Correlated signals multiply risk /P0 scores | Cause groups and maximum-per-track | Fix aggregator; rerun scoring only, not video extraction. | Scoring |
| RSK11 |Retention curve mistaken for measured forecast /P0 product | Label, assumptions acknowledgement, no fake confidence | Remove unsupported numeric claim; keep diagnostic evidence. Reopen empirical model only with labels. | Product |
| RSK12 |vRetention mislabeled ground truth /P0 science | Typed metric_kind and source provenance | Separate replay experiment; do not use as drop-off target. | Evaluation |
| RSK13 |Edited media misaligned with old evidence /P0 | Asset byte hashes and source timeline | New asset/run; compare lineage, not raw timestamp equality. | Data |
| RSK14 |Cut/move removes prerequisite /P1 | Dependency/context validation | needs_reanalysis; external editor checks; no automatic winner. | Editing |
| RSK15 |No Cerebras model access/429 /P1 | One capability probe, server secret, deadlines | Preserve extraction; partial narrative or genuine cached results; no guessed model substitutions. | API |
| RSK16 |Malicious/oversized ZIP or prompt text /P0 | Streaming limits, canonical paths, schema, untrusted text | Reject import atomically; no code/tool execution from model/video content. | API |
| RSK17 |Time/budget exceeds hackathon /P0 delivery | Vertical slice before extension, measured runtime forecast | Drop optionalP2 detectors, then polish; retain evidence/labels/core retention view. | Product |
| RSK18 |Tiny evaluation set overfitted /P0 claim | Video-level split, freeze, raw denominators | Qualify claims to tested examples; gather new independent videos later. | Evaluation |
| RSK19 |Sampling misses short defect /P1 | Uniform baseline + shot frames + capped refinement | Mark temporal resolution, never claim exhaustive frame-by-frame perception. | Vision |
| RSK20 |Proxy timing/codec fails /P0 review | Probe and mapping checks, local browser playback | One explicit transcode; source-mapped evidence and disable unsupported precision. | Media |
| RSK21 |Optional feature becomes hidden dependency /P1 | Feature catalogue + required stage list | Partial flags not blank zeros; no dependency on music/emotion/diarization. | Architecture |
| RSK22 |Package/lock unavailable upstream /P1 | Cached verified wheels/models/manifests | Use verified cache; review alternative pin/profile as new qualification, no mutable main. | Runtime |

## Explicit backlog

B01 empirical retention model trained/evaluated on authentic creator curves; depends on data agreements, audience-context handling and metric definition. B02 vlogs and additional languages after category-specific annotation. B03 reliable music/SFX/beat analysis. B04 full camera-motion and shot-transition classification. B05 face/gesture tracking only if meaningful value demonstrated; no psychological inference. B06 scalable GPU serving and automatic uploads. B07 external-editor integrations/rendering. B08 accessible polished responsive UI, animation, detailed design mocks and reportPDF. B09 licensed B-roll search, generation and TTS; outside current product goal. B10 production authentication, isolation, storage lifecycle and cloud deployment. B11 multi-creator calibration and statistically meaningful intervention studies. None is implicitly included inP3.

## Rethink checkpoints

After first clip: if image inputs, timestamps or dependency locks fail, fix foundation before UI. After first complete video: if most flags restate obvious raw metrics or lack useful edits, revise the evidence/prompt rubric before adding signals. After development evaluation: if VLM adds no useful precision/coverage over transcript-only, narrow its task to visual evidence and reconsider model choice. Before batch: if throughput or hardware budget fails, revise profile/video count explicitly. Before judge freeze: any unresolved misleading percentage claim blocks release even if the chart looks convincing.

## Open items with bounded resolution

Actual Colab GPU/driver is unknown until allocation: resolve at first preflight. Actual accessible Cerebras model is unknown: resolve by one metadata/capability probe during implementation. Final transitive dependency pins/wheel compatibility are unknown: resolve at environment qualification. Hindi OCR recognizer availability under exactPaddle release: verify one crop before bulk processing; if not, mark OCR partial and qualify an alternative in isolation. Authentic retention labels are currently unavailable: not a user permission blocker, but an empirical-accuracy gap. Remaining hackathon hours/team size are unspecified: implementation sequence is gate-based rather than pretending a calendar estimate is reliable.
