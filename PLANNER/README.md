# PS5 — Retention Predictor: implementation specification

Planning baseline: 2026-10-03. Status: **proposed build specification; no application or Colab runtime has been implemented or tested**. Owner: hackathon team. Audience: implementer, product owner, and evaluating judge.

The product diagnoses editable causes of possible audience drop-off before publishing. It combines timestamped speech, measured video/audio signals, bounded visual observations, and editorial reasoning. It presents an uncalibrated retention scenario alongside evidence-backed risk; it does not claim to know actual viewers' behaviour.

## Read and implement in this order

1. [PRD](PRD.md): product, three phases, requirements, boundaries and acceptance.
2. [Decisions](DesignDecisions.md): choices and reasons, model alternatives, UI constraints.
3. [Features](FEATURES.md): complete disposition of the user's 64 signals and the added analyses.
4. [Technical requirements](TRD.md): architecture, dependencies, temporal processing and API contracts.
5. [Schema](Schema.md): canonical data, package structure, validation, lineage and edit semantics.
6. [Retention model](RETENTION_MODEL.md): exact risk/retention calculations and presentation limits.
7. [Colab runbook](COLAB_RUNBOOK.md): hardware gates, model loading, batch execution and bounded recovery.
8. [Validation](VALIDATION.md): product checks, annotations, calibration boundaries and demonstration.
9. [Implementation sequence](IMPLEMENTATION_PLAN.md): ordered build tasks and exit gates.
10. [Module ownership](MODULES.md): responsibilities and intended code layout.
11. [Risks and backlog](RISKS.md): failure handling, triggers for rethinking, deferred work.
12. [Research](RESEARCH.md): primary sources, inspected versions and unresolved runtime evidence.
13. [Brand and product experience](BRAND_DESIGN.md): screen layouts, visual hierarchy, progressive disclosure, interaction states and design acceptance.
14. [Original UI guide](UI_REFERENCE.md): verbatim user reference for palette and visual components.

## Authority and change control

PRD owns scope, FEATURES owns feature phase/status, Schema owns field/enumeration contracts, RETENTION_MODEL owns formulas, COLAB_RUNBOOK owns runtime profiles and recovery budgets, TRD owns component interfaces, and BRAND_DESIGN owns screen layout and interaction hierarchy. DesignDecisions records why; UI_REFERENCE supplies the original visual palette. Other files link to these authorities rather than overriding them. In conflicts, stop the affected implementation, record the discrepancy, and reconcile these documents before proceeding. Direct subsequent user instructions supersede this baseline.

Use requirement IDs, feature IDs and decision IDs in implementation tasks. Do not silently promote a deferred feature. A hardware/model/schema change creates a new run or specification revision; it never relabels an old result. "Required" means a build requirement, not a claim that it currently exists. A "target" is a proposed acceptance threshold, not measured performance.

## Three delivery gates

- **Phase 1 — Diagnose:** one complete video through the manual Colab → ZIP → website flow, script-only mode, grounded issues, baseline retention scenario, simple review interface.
- **Phase 2 — Improve:** stronger multimodal checks, evidence chat, editable plan, hypothetical comparisons, selective reruns and independently reanalysed edited uploads.
- **Phase 3 — Demonstrate and evaluate:** 4–5 genuine video analyses, frozen validation, failure recovery and offline judge demonstration. Optional actual retention import only if authentic data becomes available.

All three phases remain a hackathon prototype, not a publishing platform. Do not start visual polish before Phase 1 acceptance. Do not start an optional model experiment before the primary runtime feasibility gate.

## Decisions that cannot be settled by reading documentation alone

Unquantized Qwen3.5-27B is the preferred profile, requiring 80GB-class hardware and an actual measured smoke test. Colab Pro does not guarantee that hardware. The planned 40GB fallback is Qwen3.5-9B BF16 with a visible capacity label; quality must pass the same clip rubric. If neither profile passes, ship clearly marked partial analysis or use previously completed genuine packages; do not fabricate visual observations. No quantization is enabled by this specification.

The package versions below are researched **candidate pins**, not a tested dependency lock. The first implementation milestone resolves and freezes all transitive dependencies in isolated environments and runs a bounded real GPU probe. No amount of PRD research can guarantee Colab's future driver, allocation or kernel state. The runbook prevents blind repetition when that gate fails.
