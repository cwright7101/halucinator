# Firmware Re-Hosting Fleet — orchestration guide

How multiple agents each take **one firmware** and drive it to a **real device running**
(boots its real application; a real client gets real responses over the device's own
protocol), the way the M340 PLC was done.

- **Methodology (read first):** [`arm-vxworks-plc/PLAYBOOK.md`](arm-vxworks-plc/PLAYBOOK.md)
  — the firmware-agnostic bare-march loop (run → classify → locate the gate → model the
  minimum → re-run), the toolbox, stall classification, the VxWorks track, and named dead-ends.
- **Worked example / template:** [`arm-vxworks-plc/`](arm-vxworks-plc/) — copy its shape.
- **Live queue & status:** [`REHOSTING_QUEUE.md`](REHOSTING_QUEUE.md) — claim a firmware here.
- **Kickoff prompt:** [`KICKOFF_TEMPLATE.md`](KICKOFF_TEMPLATE.md) — what to hand a new agent.
- **Spawn helper:** `new_rehost.sh <name> <public|private> [bin-path]` — makes the branch +
  worktree, stamps the dir, copies the firmware in, prints the kickoff prompt.

## The execution model
**One agent : one firmware : one branch : one worktree.** A rehost is long and
human-in-the-loop, so it is NOT a single fan-out — each firmware gets a dedicated agent.

- Base branch: **`feature/rehost-fleet`** (= `integration/post-30-32` + this fleet infra;
  `integration` = master + the assumed-merged PRs #30 x86 and #32 ARM/VxWorks).
- Each agent works in its own worktree `../hal-rehost-<name>` on its own branch.

## Definition of done — milestones (report these in the firmware's `STATUS.md`)
- **M0** bare boot reaches reset / first fault
- **M1** OS/runtime up (multitasking, or the main loop)
- **M2** application layer reached (the device's real app task)
- **M3** protocol/network served (Modbus/UMAS/HTTP/CAN/…), a client can connect
- **M4** real client round-trip → device-identifying response *(the bar; M340 hit this)*

## Per-firmware deliverable contract (mirror `arm-vxworks-plc/`)
Each `test/firmware-rehosting/<name>/` must contain:
- `<name>_config.yaml` — symbol-driven HAL config
- `extract_symbols.py` → `symbols.csv` *(gitignored, regenerable)* — for symbol-bearing OSes (VxWorks)
- `run_cfg.py` — **bounded** runner (`RUN_CFGS=`, `VERIFY_SECS=`); always watchdog the run
- `README.md` — how to reproduce from a fresh checkout
- `STATUS.md` — current **milestone + frontier (the exact gate) + dead-ends tried** (so the next
  session resumes instantly — this is what made M340 resumable)
- `PROVENANCE.md` + `licenses/` — **required for downloaded firmware** (source URL, date, sha256, license)
- `.gitignore` — exclude the binary, `symbols.csv`, `*.log`, `tmp/` — **firmware binaries are NEVER committed**

## Branch / push / provenance policy
| Firmware | Branch | Push |
|---|---|---|
| Public / open (P2IM, GRBL, OpenPLC, …) | `feature/rehost-<name>` | allowed (PROVENANCE + license committed) |
| Proprietary (Schneider, SAGE, vendor blobs) | `private/rehost-<name>` | **blocked** by `.git/hooks/pre-push` |

Binaries are gitignored in BOTH cases. For downloaded firmware, write `PROVENANCE.md` (URL, date,
sha256, license) and drop the license in `licenses/` **before** any work. Only publicly
redistributable images go on a pushable `feature/` branch.

## Spawn recipe (manual equivalent of `new_rehost.sh`)
```bash
# from the repo root, on/with feature/rehost-fleet available
git worktree add -b feature/rehost-<name> ../hal-rehost-<name> feature/rehost-fleet   # or private/rehost-<name>
cp <source>/<firmware>  ../hal-rehost-<name>/test/firmware-rehosting/<name>/<name>.bin  # gitignored
# stamp the dir from arm-vxworks-plc/, edit config for the target, then hand the agent KICKOFF_TEMPLATE.md
```
> **Gotcha:** the firmware binaries live untracked in the *main* checkout
> (`/Users/user/Development/emulation/halucinator/test/firmware-rehosting/<name>/`). They do NOT
> travel to a fresh worktree — you must copy the binary in.

## Guardrails every agent gets
- Bound every run; `pkill -9 -f run_cfg` (or your runner) between iterations — stray emulators
  silently 10× the boot time.
- Cross-validate a fault under both `unicorn` and `avatar-qemu` before modeling around it (§2).
- Don't touch other agents' worktrees/branches. Don't modify `integration/post-30-32` or
  `feature/rehost-fleet` themselves — only build on top.
- No Claude/Anthropic attribution in commits; never stage `CLAUDE.md` / `.claude/`.
