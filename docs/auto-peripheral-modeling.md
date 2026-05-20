# Automatic peripheral-model generation for HALucinator

> Status: **Phases 0–4 implemented and demonstrated on real firmware.**
> The runtime half is `peripheral_models/auto_model.py`
> (RecordingPeripheral / AutoPeripheral), wired into the unicorn path; the
> offline half is `halucinator.automodel.synthesize`; the LLM layer is
> `halucinator.llm` (pluggable provider). Demonstrated on the GRBL CNC
> (`test/firmware-rehosting/cnc-grbl/run_tests_auto.bash`) and the
> STM32F103 robot (`test/firmware-rehosting/robot-stm32/`). The remaining
> gap is the symbolic-refinement value heuristic needed for fully
> unattended boot of busy-wait-on-RAM / clock-compute code — see
> "Effort / risk".

## Motivation

Rehosting firmware today is manual. The `test/firmware-rehosting/cnc-grbl/`
case is representative: to boot a real GRBL CNC controller we hand-wrote
intercepts after reading disassembly — neutralise the clock/PLL spin-wait
(`SystemClock_Config`), the SysTick wait, the USART `TXE` busy-loop
(`usart_putc`), and the P2IM AFL hypercall (`aflCall`). Every new firmware
repeats that detective work.

The goal: **observe what the firmware does to its peripherals, infer a
model, and synthesize the intercepts/peripheral-model automatically**, so a
new firmware boots with little or no hand-authoring.

HALucinator already owns the hard part — *observability*. Every unmodeled
MMIO access funnels through one choke point per backend:

- `UnicornBackend._make_mmio_hook` (`src/halucinator/backends/unicorn_backend.py`)
  — sees `(offset, size)` on read, `(offset, size, value)` on write.
- avatar2 `_MMIOForwardingDispatcher` (`src/halucinator/main.py`) — sees
  `(addr, size, num_words, raw)` reads / `(addr, size, value)` writes.
- `GenericPeripheral` (`src/halucinator/peripheral_models/generic.py`)
  already records *unique* accessed addresses to `hal_stats`; it returns 0
  on read and swallows writes.

What's missing is **record → infer → synthesize → validate**, not the hooks.

## Prior art

| System | Year | Technique | LLM? |
|---|---|---|---|
| **P2IM** | 2020 | Heuristic register classification (control/status/data) by access pattern | No |
| **μEmu** | 2021 | Symbolic exec; learn return values that avoid invalid states; cache a knowledge base | No |
| **Fuzzware** | 2022 | Per-access dynamic symbolic exec to find which MMIO bits matter; model the rest as fuzz input | No |
| **Perry** | 2024 | Program analysis on *driver source* to synthesize peripheral models for QEMU | No |
| **FlexEmu** | 2025 | Per-category abstract models for higher-fidelity MCU peripheral emulation | Partial |
| **ADFEmu** | 2025 | Concolic execution **+ LLM** to emulate DMA and synthesize peripheral input sequences | **Yes** |

The takeaway: classical auto-modeling (P2IM → Fuzzware → Perry) used
heuristics / symbolic execution. The 2025 wave (ADFEmu, and the broader
"datasheet → driver/model" line of work) brings LLMs in for the *semantic*
step — reading register meaning out of human-facing text and reasoning
about what a read should return. That semantic step is exactly where pure
heuristics struggle.

## Architecture

```
                 ┌─────────────────────────────────────────┐
                 │  HALucinator backend (unicorn/qemu/...)   │
                 │  MMIO choke point  ──►  RecordingPeripheral│
                 └───────────────┬───────────────────────────┘
                                 │  mmio_trace (SQLite)
                                 ▼
        ┌──────────────────────────────────────────────────┐
        │  Inference                                         │
        │   • heuristic classifier (P2IM-style)              │
        │   • optional symbolic refinement (angr, already a  │
        │     dep)                                            │
        │   • optional LLM modeler (datasheet/SVD + trace +  │
        │     disasm)  ── via pluggable LLMProvider          │
        └───────────────┬──────────────────────────────────┘
                         │  proposed model + intercepts
                         ▼
        ┌──────────────────────────────────────────────────┐
        │  Synthesize: emit peripheral_models/* class +      │
        │  intercepts YAML (reviewable artifacts)            │
        └───────────────┬──────────────────────────────────┘
                         │
                         ▼  re-run firmware
        ┌──────────────────────────────────────────────────┐
        │  Validate (the emulator is the oracle):            │
        │   progressed? stalled? faulted?  ──► feed back     │
        └──────────────────────────────────────────────────┘
```

### Phases

**Phase 0 — `RecordingPeripheral` (small, ~1 day).** A `GenericPeripheral`
subclass that logs `(order, pc, addr, size, value, rw)` to a SQLite
`mmio_trace` table, reusing `State_Recorder`'s SQLite infra
(`src/halucinator/util/profile_hals.py`). Gated by a `--record-mmio` flag.
Pure observation; immediately useful on its own.

**Phase 1 — heuristic classifier.** Offline pass over the trace, using the
basic-block graph (`src/tools/graph_qemu_trace.py`) for control-flow
context. P2IM-style rules: a register read in a tight polling loop that
gates a branch → **status** (model "ready"); a read whose value flows into
stored/processed data → **data** (input source); write-only → **control**.

**Phase 2 — synthesis.** Emit either a `peripheral_models/` class +
`intercepts.yaml` (reviewable, exactly like the hand-written cnc-grbl
files), or a runtime `AutoPeripheral` applying the learned policy.

**Phase 3 — runtime stall-breaker loop (μEmu-lite).** Detect a stall (same
MMIO read in a tight loop ≥ N times = busy-wait), apply the "return the
value that breaks the loop" heuristic, persist to a knowledge base,
continue. This would have auto-neutralised the cnc-grbl
`SystemClock_Config` / `usart_putc` spin-waits.

**Phase 4 — LLM-assisted modeling (see below).** Use an LLM for the
*semantic* inference Phases 1–3 can't do: read register meaning from a
datasheet / SVD / CMSIS header, classify ambiguous registers, and propose
intercept policies — with the emulator validating every proposal.

## Phase 4: LLM-assisted modeling via the MCP server

The `feature/halucinator-mcp` branch already exposes the emulation as
LLM-callable tools (MCP). That is the substrate: an LLM drives the
record→infer→synthesize→validate loop by *calling emulator tools*, not by
one-shot code generation.

```
LLM ──(MCP tools)──► propose model / intercept / register policy
        │
        ▼
   run firmware (backend)  ──►  read mmio_trace + run state
        │
        ▼
   observe: progressed / stalled-at / faulted-at   ← deterministic oracle
        │
        ▼
   feed result back to LLM  ──►  refine  ──►  repeat
```

Why this is safe: the emulator is a cheap, deterministic verifier. An LLM
hallucination ("this is a status register, return 0x80") is caught
immediately by "firmware still hangs at the same PC." The LLM proposes;
the rehost disproves. Contrast with one-shot LLM code-gen, which has no
oracle.

**Where the LLM is used (offline / proposal only — never the per-access
hot path):**

1. **Datasheet / SVD / CMSIS-header → model.** Register maps are often
   machine-readable (CMSIS-SVD XML). Feed the SVD + the observed trace to
   the LLM; it emits a `peripheral_models/` class with real register
   semantics instead of a return-0 catch-all. Strongest LLM fit — the
   meaning lives in text heuristics can't see.
2. **Trace + disassembly → register classification.** "Given this access
   trace at `0x40004400` and the disassembly of the accessing function,
   is this status/data/control and what should a read return to make
   progress?"
3. **Intercept-list proposal.** From the symbol table + disassembly,
   propose which functions to intercept and the return policy — automating
   `cnc_config.yaml`.

The stall detector and per-access hot path stay deterministic; the LLM is
only invoked offline between runs.

## Pluggable LLM provider

Per the requirement to **swap which LLM is used**, the LLM is reached
through a thin provider abstraction, never a hard-coded vendor SDK.

```
src/halucinator/llm/
    __init__.py        # get_provider(config) factory
    base.py            # LLMProvider ABC
    anthropic.py       # Claude (Anthropic API)
    openai.py          # OpenAI / Azure OpenAI
    google.py          # Gemini
    ollama.py          # local models (Ollama / llama.cpp server)
    mock.py            # deterministic stub for tests / offline CI
```

```python
class LLMProvider(ABC):
    @abstractmethod
    def complete(self, system: str, prompt: str,
                 *, tools: list | None = None,
                 max_tokens: int = 4096) -> LLMResponse: ...
```

Selection is config- and env-driven so no code change is needed to switch:

```yaml
# in the halucinator config (machine: or a new llm: block)
llm:
  provider: anthropic          # anthropic | openai | google | ollama | mock
  model: claude-opus-4-7       # provider-specific model id
  base_url: null               # override for self-hosted / Azure / Ollama
  api_key_env: ANTHROPIC_API_KEY   # name of the env var holding the key
  max_tokens: 4096
  temperature: 0
```

```
# env overrides win over config, so CI / local can swap without edits:
HALUCINATOR_LLM_PROVIDER=ollama
HALUCINATOR_LLM_MODEL=qwen2.5-coder:32b
HALUCINATOR_LLM_BASE_URL=http://localhost:11434
```

Rules:
- **No hard dependency on any one vendor.** Each provider module imports
  its SDK lazily; the package works with zero LLM SDKs installed (the
  `mock` provider and the non-LLM phases still run).
- **Keys only from env**, named by `api_key_env`; never stored in config
  or committed.
- **`mock` provider** returns canned responses so the modeling pipeline is
  testable in CI without network or keys.
- The MCP server (`feature/halucinator-mcp`) consumes the same provider
  config, so the interactive and batch paths share one knob.

## Effort / risk

| Phase | Effort | Risk | Value |
|---|---|---|---|
| 0 RecordingPeripheral | ~1 day | low | data source for everything else |
| 1 heuristic classifier | ~3–5 days | medium | covers the common status/data/control cases |
| 2 synthesis | ~3 days | medium | produces reviewable artifacts |
| 3 stall-breaker loop | ~1 week | medium-high | auto-boots busy-wait-heavy firmware |
| 4 LLM modeling + provider | ~1–2 weeks | medium | semantic inference; needs the validation loop to stay honest |

angr is already a dependency, so a Fuzzware/μEmu-style symbolic path needs
no new heavy deps. The LLM provider adds optional, lazily-imported SDKs.

Start with Phase 0 — it is cheap, independently useful (turns the catch-all
into a labelled trace), and is the input every later phase consumes.

## References

- ADFEmu — DMA input emulation with concolic execution + LLMs (2025).
- FlexEmu — flexible per-category MCU peripheral emulation (2025).
- Perry — peripheral model synthesis via driver program analysis (2024).
- Fuzzware — per-access symbolic MMIO modeling (USENIX Security 2022).
- μEmu — learning peripheral behavior via symbolic execution (USENIX 2021).
- P2IM — processor/peripheral-in-the-loop heuristic modeling (USENIX 2020).

(See the chat thread / commit message for the source URLs gathered during
this research; verify exact venues/links before citing externally.)
