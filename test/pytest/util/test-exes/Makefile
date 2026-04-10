CFLAGS=-g -Os

all: test-arm.s
.PHONY: all

test-arm.elf: test.c support.c
	arm-none-eabi-gcc -static $(CFLAGS) -o$@ $^

test-arm.gtirb: test-arm.elf
	ddisasm --ir $@ $^

test-arm.s: test-arm.gtirb
	gtirb-pprinter --listing-mode=ui --asm $@ $^

clean:
	rm -f test-arm.s test-arm.gtirb test-arm.elf
