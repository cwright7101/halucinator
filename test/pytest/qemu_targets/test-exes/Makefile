CFLAGS=-g

all: test-x64.elf test-arm.elf test-arm.bin
.PHONY: all

test-x64.elf: test.c
	$(CC) $(CFLAGS) -static -o$@ $^

test-arm.elf: test.c support.c
	arm-none-eabi-gcc -static $(CFLAGS) -o$@ $^

test-arm.bin: test-arm.elf
	arm-none-eabi-objcopy -O binary $< $@
