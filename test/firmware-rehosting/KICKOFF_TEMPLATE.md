# Kickoff prompt template (fill the <…> and paste to the new rehost agent)

```
You are re-hosting ONE firmware to a real-device-running state, using HALucinator.

Workspace:  cd <WORKTREE>            # e.g. /Users/user/Development/emulation/hal-rehost-<name>
Branch:     <BRANCH>                 # feature/rehost-<name> (public) | private/rehost-<name> (proprietary)
Firmware:   test/firmware-rehosting/<name>/<bin>     (arch: <ARCH>, OS: <OS/bare-metal>)
Source:     <public benchmark | proprietary | downloaded-from-URL>

READ FIRST, in order:
  1. test/firmware-rehosting/REHOSTING.md          (fleet rules, milestones, deliverable contract)
  2. test/firmware-rehosting/arm-vxworks-plc/PLAYBOOK.md   (the METHOD — bare-march loop, §4 toolbox,
                                                            §5 classify, §6 VxWorks track, §8 dead-ends)
  3. test/firmware-rehosting/arm-vxworks-plc/      (the worked example to mirror)

GOAL: drive this firmware to milestone M4 — boots its real application AND a real client gets a
real, device-identifying response over the device's own protocol. Report milestones M0→M4.

METHOD: bare-march. Start bare (real RAM + reset vector only), run, classify each stall
(fault / busy-spin / pend), locate the exact gate, model the MINIMUM to pass it, re-run. Never
fabricate kernel state the firmware should build itself (see PLAYBOOK §1.1 / §8).

SET UP THE DELIVERABLE (mirror arm-vxworks-plc/): <name>_config.yaml, extract_symbols.py (if the OS
ships a symbol table — recover it FIRST, it's worth more than anything else), run_cfg.py (bounded),
README.md, STATUS.md, .gitignore (binary + symbols.csv + logs).

KEEP STATUS.md CURRENT every iteration: milestone, the exact frontier gate (fn/PC + why it blocks),
and dead-ends tried. This is what makes the work resumable across sessions.

GUARDRAILS:
- Bound every run (watchdog / VERIFY_SECS). `pkill -9 -f run_cfg` between runs — stray emulators
  silently make boots ~10× slower.
- Cross-validate a real fault under both --emulator unicorn AND avatar-qemu before modeling past it.
  (On macOS the qemu binary is Linux-only — iterate in unicorn; see REHOSTING.md "Host environment".)
- ⚠ FRAMEWORK EDITS: `halucinator` runs from the MAIN checkout's src, NOT your worktree. To patch
  src/halucinator/* from your worktree, edit your worktree's copy AND prepend it to PYTHONPATH (see
  p2im-drone/run_cfg.py); prefer env-var hooks. NEVER edit the main checkout's src (it's the user's
  branch). Read REHOSTING.md "Host environment & gotchas" before touching framework code.
- PUSH POLICY: <public → may push this branch> | <proprietary → NEVER push; pre-push hook blocks
  private/*; do not use --no-verify>.
- Firmware binaries are NEVER committed (they're gitignored). For downloaded firmware, commit
  PROVENANCE.md (URL/date/sha256/license) + the license first.
- Stay in YOUR worktree. Don't touch other worktrees/branches, integration/post-30-32, or
  feature/rehost-fleet. No Claude/Anthropic attribution in commits; never stage CLAUDE.md/.claude.
- Update your row in test/firmware-rehosting/REHOSTING_QUEUE.md (status/milestone/frontier).

Before deep work, confirm the target's arch/OS and the intended protocol/end-goal, then report your
first milestone (M0 bare boot) and the first gate you hit.
```
