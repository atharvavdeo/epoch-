"""Deterministic risk aggregation and retention scenarios (RETENTION_MODEL.md).

Pure Python (math only) so both the pipeline and the local API compute the
identical numbers. No LLM output ever enters these formulas except through
validated Issue records.
"""

FORMULA_VERSION = "scenario-survival-v1"
RISK_VERSION = "risk-max-per-track-v1"
