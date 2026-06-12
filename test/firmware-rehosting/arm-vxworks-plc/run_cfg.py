"""Bounded native runner. Configs via RUN_CFGS (comma-separated -c list);
watchdog os._exit()s after VERIFY_SECS so a still-spinning stack doesn't hang."""
import os
import sys
import threading

DEADLINE = int(os.environ.get("VERIFY_SECS", "150"))
CFGS = os.environ.get("RUN_CFGS", "arm-vxworks-plc_config.yaml").split(",")


def _watchdog():
    os.write(2, b"RUN: watchdog fired -- exiting\n")
    os._exit(0)


threading.Timer(DEADLINE, _watchdog).start()

argv = ["hal"]
for c in CFGS:
    argv += ["-c", c]
argv += ["-s", os.environ.get("RUN_SYMS", "symbols.csv"), "--emulator", "unicorn"]
sys.argv = argv

from halucinator import main  # noqa: E402

main.main()
