"""Colab VLM runtime (shipped inside every visual job bundle).

Only this package, the prompt templates and the vlm lock run on Colab. It
depends on pydantic (+ torch/transformers for the real backend), never on
the rest of the repository, so the bundle is self-contained.
"""

JOB_PROTOCOL = "epoch-visual-job/1"
RESULT_PROTOCOL = "epoch-visual-result/1"
BOOTSTRAP_PROTOCOL = 1  # notebook <-> runtime contract; bump only if notebook cells must change
