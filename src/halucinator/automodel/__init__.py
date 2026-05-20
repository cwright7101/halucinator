"""Automatic peripheral-model synthesis from recorded MMIO traces.

See docs/auto-peripheral-modeling.md for the full design. The runtime
half (RecordingPeripheral / AutoPeripheral) lives in
halucinator.peripheral_models.auto_model; this package is the offline
half: read the `mmio_trace` SQLite produced by a recording run, classify
registers, and emit a reviewable model/config (optionally LLM-assisted
via halucinator.llm).
"""
from .synthesize import RegisterModel, synthesize_from_db  # noqa: F401
