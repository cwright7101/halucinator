"""Offline synthesizer: MMIO trace -> classified register model -> YAML.

Reads the `mmio_trace` table written by RecordingPeripheral/AutoPeripheral
(halucinator.peripheral_models.auto_model), classifies each register by
access pattern (P2IM-style heuristics), and emits a reviewable model. An
optional LLM pass (via the pluggable halucinator.llm provider) adds a
semantic label / suggested return policy per register.

Usage:
    python -m halucinator.automodel.synthesize <mmio_trace.sqlite> \
        [-o model.yaml] [--llm] [--llm-provider ollama] [--llm-model ...]
"""
from __future__ import annotations

import argparse
import collections
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RegisterModel:
    addr: int
    reads: int = 0
    writes: int = 0
    distinct_write_values: int = 0
    printable_writes: int = 0
    # Max consecutive reads from the same pc (busy-wait signal).
    max_consecutive_reads: int = 0
    read_pcs: set = field(default_factory=set)
    write_pcs: set = field(default_factory=set)
    klass: str = "unknown"          # status | data_out | data_in | control
    suggested_policy: str = ""
    llm_label: str = ""

    def classify(self) -> None:
        """Heuristic register classification (no LLM).

        Order matters: a register polled in a spin-wait is classified as
        `status` first (that's the actionable signal for booting), even if
        it is also written — many control registers (e.g. RCC->CR) are both
        configured and polled for a ready bit.
        """
        printable_ratio = (self.printable_writes / self.writes) if self.writes else 0.0
        # Pure data-out (write stream of printable bytes, never read) is an
        # unambiguous UART TX; catch it before the status check.
        if self.writes and self.reads == 0 and printable_ratio > 0.6:
            self.klass = "data_out"
            self.suggested_policy = "capture writes as UART/console output"
        elif self.max_consecutive_reads >= 8:
            self.klass = "status"
            self.suggested_policy = (
                "polled in a spin-wait; return all-ones to satisfy "
                "wait-for-SET (or 0 for wait-while-BUSY)")
        elif self.writes and printable_ratio > 0.6:
            self.klass = "data_out"
            self.suggested_policy = "capture writes as UART/console output"
        elif self.reads and self.writes == 0:
            self.klass = "data_in"
            self.suggested_policy = "model as input source (fuzzable)"
        elif self.writes and self.reads == 0:
            self.klass = "control"
            self.suggested_policy = "writes configure the device; ignore on read"
        else:
            self.klass = "control"
            self.suggested_policy = "mixed read/write control register"


def _load(db_path: str) -> List[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT seq, pc, addr, size, value, rw FROM mmio_trace ORDER BY id"
        ).fetchall()
    finally:
        conn.close()


def _build_models(rows: List[tuple]) -> Dict[int, RegisterModel]:
    models: Dict[int, RegisterModel] = {}
    # Track consecutive same-(pc,addr) read runs for the busy-wait signal.
    run_key = None
    run_len = 0
    for _seq, pc, addr, _size, value, rw in rows:
        m = models.setdefault(addr, RegisterModel(addr=addr))
        if rw == "r":
            m.reads += 1
            m.read_pcs.add(pc)
            key = (pc, addr)
            if key == run_key:
                run_len += 1
            else:
                run_key, run_len = key, 1
            m.max_consecutive_reads = max(m.max_consecutive_reads, run_len)
        else:
            m.writes += 1
            m.write_pcs.add(pc)
            low = value & 0xFF
            if low in (0x0A, 0x0D) or 0x20 <= low < 0x7F:
                m.printable_writes += 1
            run_key, run_len = None, 0
    # distinct write values per addr
    wvals = collections.defaultdict(set)
    for _seq, _pc, addr, _size, value, rw in rows:
        if rw == "w":
            wvals[addr].add(value)
    for addr, m in models.items():
        m.distinct_write_values = len(wvals.get(addr, ()))
        m.classify()
    return models


def _llm_annotate(models: Dict[int, RegisterModel], llm_config: Dict[str, Any]) -> None:
    """Optional: ask the configured LLM for a semantic label per register."""
    from halucinator.llm import get_provider
    provider = get_provider(llm_config)
    system = (
        "You are an embedded-systems reverse engineer. Given an MMIO "
        "register access summary, reply with one short line: the likely "
        "register role and what a read should return for the firmware to "
        "make progress. Be concise.")
    for m in sorted(models.values(), key=lambda x: x.addr):
        prompt = (
            f"addr=0x{m.addr:08x} reads={m.reads} writes={m.writes} "
            f"distinct_write_values={m.distinct_write_values} "
            f"max_consecutive_reads={m.max_consecutive_reads} "
            f"heuristic_class={m.klass}")
        try:
            m.llm_label = provider.complete(system, prompt, max_tokens=120).text.strip()
        except Exception as exc:  # noqa: BLE001
            m.llm_label = f"<llm error: {exc}>"


def synthesize_from_db(db_path: str,
                       llm_config: Optional[Dict[str, Any]] = None
                       ) -> Dict[int, RegisterModel]:
    rows = _load(db_path)
    models = _build_models(rows)
    if llm_config is not None:
        _llm_annotate(models, llm_config)
    return models


def to_yaml(models: Dict[int, RegisterModel]) -> str:
    lines = ["# Auto-synthesized peripheral model (from MMIO trace)",
             "registers:"]
    for m in sorted(models.values(), key=lambda x: x.addr):
        lines.append(f"  - addr: 0x{m.addr:08x}")
        lines.append(f"    class: {m.klass}")
        lines.append(f"    reads: {m.reads}")
        lines.append(f"    writes: {m.writes}")
        lines.append(f"    max_consecutive_reads: {m.max_consecutive_reads}")
        lines.append(f"    policy: {m.suggested_policy!r}")
        if m.llm_label:
            lines.append(f"    llm: {m.llm_label!r}")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("db", help="path to mmio_trace.sqlite from a recording run")
    ap.add_argument("-o", "--out", help="write YAML model here (default: stdout)")
    ap.add_argument("--llm", action="store_true",
                    help="annotate each register with an LLM label")
    ap.add_argument("--llm-provider", default=None,
                    help="anthropic|openai|google|ollama|mock (default: mock)")
    ap.add_argument("--llm-model", default=None)
    args = ap.parse_args(argv)

    llm_config = None
    if args.llm:
        llm_config = {"provider": args.llm_provider or "mock"}
        if args.llm_model:
            llm_config["model"] = args.llm_model
    models = synthesize_from_db(args.db, llm_config)
    out = to_yaml(models)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(out)
        print(f"wrote {args.out} ({len(models)} registers)")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
