# Re-Hosting Queue & Status

Claim a firmware by filling its **Agent / Branch / Worktree** and setting **Status** to
`in-progress`. Update **Milestone** (M0–M4, see `REHOSTING.md`) + **Frontier** as you go.
One agent per row. Don't double-book a row.

Status: `todo` · `in-progress` · `blocked` · `done`  ·  Milestone: M0–M4

## Track A — public benchmark firmware (pushable `feature/rehost-<name>`)
| Firmware | Bin | Arch / OS (confirm) | Status | Milestone | Agent / Branch / Worktree | Frontier |
|---|---|---|---|---|---|---|
| p2im-drone | Drone.elf | ARM Cortex-M / bare-metal | in-progress | M0 | PILOT / `feature/rehost-p2im-drone` / `../hal-rehost-drone` | (kickoff) |
| cnc-grbl | CNC.bin | ARM Cortex-M / GRBL (open) | todo | — | — | — |
| console-kinetis | Console.elf | Kinetis / bare-metal | todo | — | — | — |
| gateway-stm32 | Gateway.elf | STM32 | todo | — | — | — |
| heatpress-sam3x | Heat.elf | SAM3X (Cortex-M3) | todo | — | — | — |
| plc-stm32 | PLC.bin | STM32 | todo | — | — | — |
| reflow-oven-stm32 | Reflow.bin | STM32 | todo | — | — | — |
| robot-stm32 | Robot.elf | STM32 | todo | — | — | — |
| steering-sam3x | Steering.elf | SAM3X | todo | — | — | — |

## Track B — proprietary ICS (private `private/rehost-<name>`, never push)
| Firmware | Bin | Arch / OS | Status | Milestone | Agent / Branch / Worktree | Frontier |
|---|---|---|---|---|---|---|
| m340-plc-arm | M340.bin | ARM AT91RM9200 / VxWorks 6.4 | done | M4 | (reference) / `private/m340-alt-techniques` | Modbus/UMAS :502 served |
| bmxnoe-arm | vxWorks_noe0110.bin | ARM / VxWorks (Schneider BMXNOE0110) | todo | — | — | reuse M340 intercepts (§6) |
| sage-rtu-x86 | vxWorks.elf | x86 / VxWorks (SAGE C3414 RTU) | todo | — | — | — |
| scadapack-sp350-arm | SCADAPack_350_*.bin | ARM (Schneider SCADAPack 350 TelePACE) | todo | — | — | — |
| ion-meter-arm | **MISSING** | ARM (Schneider PowerLogic ION) | blocked | — | — | needs firmware binary sourced |
| ion-meters | **MISSING** | ARM (Schneider PowerLogic ION) | blocked | — | — | needs firmware binary sourced |

## Track C — newly downloaded firmware (agents source it)
Add a row when ingesting. Required before work: `PROVENANCE.md` (URL, date, sha256, license) + license file.
Sources: P2IM / HALucinator / Pretender benchmark repos; vendor public firmware downloads; open RTOS/PLC
projects (OpenPLC, Marlin, GRBL releases); public firmware datasets.
| Firmware | Source URL | License | Status | Milestone | Agent / Branch / Worktree |
|---|---|---|---|---|---|
| _(none yet)_ | | | | | |
