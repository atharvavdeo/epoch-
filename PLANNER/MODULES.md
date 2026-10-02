# Implementation boundaries and intended repository layout

These paths describe future implementation; only planning Markdown exists now.

| Module | Owns | Must not own |
|---|---|---|
| contracts | Pydantic schemas, enums, generated JSONSchema/TS, migrations | Model calls and UI-specific ad hoc fields |
| media | Probe/decode/proxy/PTS mapping, cuts and deterministic signal extraction | Editorial verdicts |
| speech | ASR, language-aware alignment, transcript correction lineage | Fabricated word timings |
| text_vision | OCR crops/tracks and text measurements | Unsupported readability claims from single frames |
| visual | Sampling plan, frame tensors, VLM observations, bounded refinements | Audience percentages and audio claims |
| reasoning | Promise ledger, semantic candidate retrieval, grounded issue proposals and edits | Accepting its own invalid references |
| validators | Schema, evidence, temporal precision, issue deduplication | Hidden retries or silent data repair |
| scoring | Risk aggregation, retention scenario, edit timeline transforms | LLM-generated scores or fitted-model claims |
| orchestration | Fingerprints, stage graph, checkpoints, caps, exports | Open-ended autonomous planning |
| api | Import transactions, persistence, media delivery, chat adapter | Colab remote execution |
| web | Project/review/edit/evaluation UI and shared playhead | Secret keys or authoritative numeric formulas |
| evaluation | Fixtures, annotations, matching and honest metrics | Reusing held-out data invisibly for tuning |

Planned tree:

```text
PLANNER/                    authoritative specification
contracts/                  schemas, migrations, generated types
pipeline/
  media/ speech/ text_vision/ visual/ reasoning/
  validators/ scoring/ orchestration/
notebooks/                  controller notebook only; logic imported from pipeline
locks/                      separate fully resolved environment locks
prompts/                    versioned observation/narrative/chat templates
apps/api/                   local FastAPI application
apps/web/                   React website
fixtures/                   small authorised media/contract fixtures
validation/                 split manifests, annotations, reports
scripts/                    explicit setup/export utilities
```

Generated media/model caches/packages belong in configured external data directories and are not committed. `.env`/secrets are ignored and never exported. README/setup written during implementation must name tested hardware and qualification date. Boundary test: scoring can run offline from a validated package; website can review it without importing Torch/Paddle; notebook can resume without the website.
