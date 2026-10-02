"""ASR and language-aware alignment (asr environment, CPU FP32 per D16).

Never fabricates word precision: WhisperX interpolated words (no alignment
score) are stored with null times and alignment_status="unaligned".
"""
