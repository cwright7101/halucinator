ENTRY(_reset)

PHDRS
{
    text PT_LOAD ;
    data PT_LOAD ;
}

MEMORY
{
    /* Map flash at kseg0 (0x80000000-0x9FFFFFFF) which is the
     * unmapped, cached, kernel segment — no TLB required. RAM at
     * 0xA0000000 (kseg1, unmapped uncached) so MMIO/RAM both work
     * regardless of TLB state. */
    flash (rx)  : ORIGIN = 0x80000000, LENGTH = 0x10000
    ram   (rwx) : ORIGIN = 0xA0000000, LENGTH = 0x10000
}

SECTIONS
{
    .text    : { *(.text*)   } > flash :text
    .rodata  : { *(.rodata*) } > flash :text

    .data    : {
        _data_start = .;
        *(.data*)
        _data_end = .;
    } > ram AT > flash :data

    .bss : {
        _bss_start = .;
        *(.bss*) *(COMMON)
        _bss_end = .;
    } > ram :NONE

    . = ORIGIN(ram) + LENGTH(ram) - 0x10;
    _stack_top = .;
}
