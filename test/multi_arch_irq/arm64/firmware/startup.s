/*
 * AArch64 reset entry + IRQ trampoline.
 *
 * Two execution models share this firmware:
 *   - Real Cortex-A in QEMU's `virt` machine: takes the IRQ exception
 *     via VBAR_EL1 + 0x280, runs _irq_entry (which uses ERET to
 *     return). VBAR_EL1 is set in _reset.
 *   - In-process emulators (unicorn, ghidra) without a CPU exception
 *     model: the backend's synthetic IRQ entry sets LR = interrupted
 *     PC and jumps PC to _irq_entry_simple, which saves/restores
 *     registers around a C IRQ_Handler call and returns via plain
 *     `ret` (no ERET, no SPSR/ELR model needed).
 *
 * The two paths share IRQ_Handler so the C code stays single-source.
 */

    .section .vectors, "ax"
    .align 11           /* 2KB alignment required for VBAR */
    .global _vectors
_vectors:
    .balign 0x80;  b   Default_Handler   /* Sync   - SP0 */
    .balign 0x80;  b   _irq_entry_eret   /* IRQ    - SP0 */
    .balign 0x80;  b   Default_Handler
    .balign 0x80;  b   Default_Handler
    .balign 0x80;  b   Default_Handler   /* Sync   - SPx */
    .balign 0x80;  b   _irq_entry_eret   /* IRQ    - SPx */
    .balign 0x80;  b   Default_Handler
    .balign 0x80;  b   Default_Handler
    .balign 0x80;  b   Default_Handler
    .balign 0x80;  b   Default_Handler
    .balign 0x80;  b   Default_Handler
    .balign 0x80;  b   Default_Handler
    .balign 0x80;  b   Default_Handler
    .balign 0x80;  b   Default_Handler
    .balign 0x80;  b   Default_Handler
    .balign 0x80;  b   Default_Handler

    .text

    .global _reset
    .type   _reset, %function
_reset:
    ldr  x0, =_stack_top
    mov  sp, x0

    adr  x0, _vectors
    msr  vbar_el1, x0
    isb

    bl   main
1:  b 1b

    /* IRQ entry path used by real GIC + ERET delivery. */
    .global _irq_entry_eret
    .type   _irq_entry_eret, %function
_irq_entry_eret:
    sub  sp, sp, #0x100
    stp  x0,  x1,  [sp, #0x00]
    stp  x2,  x3,  [sp, #0x10]
    stp  x4,  x5,  [sp, #0x20]
    stp  x6,  x7,  [sp, #0x30]
    stp  x8,  x9,  [sp, #0x40]
    stp  x10, x11, [sp, #0x50]
    stp  x12, x13, [sp, #0x60]
    stp  x14, x15, [sp, #0x70]
    stp  x16, x17, [sp, #0x80]
    stp  x18, x29, [sp, #0x90]
    str  x30,      [sp, #0xA0]
    bl   IRQ_Handler
    ldr  x30,      [sp, #0xA0]
    ldp  x18, x29, [sp, #0x90]
    ldp  x16, x17, [sp, #0x80]
    ldp  x14, x15, [sp, #0x70]
    ldp  x12, x13, [sp, #0x60]
    ldp  x10, x11, [sp, #0x50]
    ldp  x8,  x9,  [sp, #0x40]
    ldp  x6,  x7,  [sp, #0x30]
    ldp  x4,  x5,  [sp, #0x20]
    ldp  x2,  x3,  [sp, #0x10]
    ldp  x0,  x1,  [sp, #0x00]
    add  sp, sp, #0x100
    eret

    /* IRQ entry path for in-process backends that don't model
     * exception levels: synthetic delivery sets LR = interrupted PC
     * and jumps here, we save/restore caller-saved regs and return
     * via plain `ret`. */
    .global _irq_entry_simple
    .type   _irq_entry_simple, %function
_irq_entry_simple:
    sub  sp, sp, #0x100
    stp  x0,  x1,  [sp, #0x00]
    stp  x2,  x3,  [sp, #0x10]
    stp  x4,  x5,  [sp, #0x20]
    stp  x6,  x7,  [sp, #0x30]
    stp  x8,  x9,  [sp, #0x40]
    stp  x10, x11, [sp, #0x50]
    stp  x12, x13, [sp, #0x60]
    stp  x14, x15, [sp, #0x70]
    stp  x16, x17, [sp, #0x80]
    stp  x18, x29, [sp, #0x90]
    str  x30,      [sp, #0xA0]
    bl   IRQ_Handler
    ldr  x30,      [sp, #0xA0]
    ldp  x18, x29, [sp, #0x90]
    ldp  x16, x17, [sp, #0x80]
    ldp  x14, x15, [sp, #0x70]
    ldp  x12, x13, [sp, #0x60]
    ldp  x10, x11, [sp, #0x50]
    ldp  x8,  x9,  [sp, #0x40]
    ldp  x6,  x7,  [sp, #0x30]
    ldp  x4,  x5,  [sp, #0x20]
    ldp  x2,  x3,  [sp, #0x10]
    ldp  x0,  x1,  [sp, #0x00]
    add  sp, sp, #0x100
    ret
