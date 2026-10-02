"""Media probing, proxy, PTS mapping and deterministic signal extraction.

Owns measurements only, never editorial verdicts (MODULES.md).
Source timeline zero = container start time, matching ffmpeg's default output
shift, so proxy/WAV/filter timestamps share one origin (ARCHITECTURE §4).
"""
