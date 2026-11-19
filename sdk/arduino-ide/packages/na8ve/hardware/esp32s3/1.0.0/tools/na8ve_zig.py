#!/usr/bin/env python3
"""Serialize zig toolchain invocations with an OS file lock to avoid Windows cache contention."""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

ZIG = r"C:\Espressif\tools\ziglang\ziglang\zig.exe"
if not pathlib.Path(ZIG).exists():
    ZIG = shutil.which("zig") or "zig.exe"


def _acquire_lock(lf) -> None:
    if os.name == "nt":
        import msvcrt
        while True:
            lf.seek(0)
            try:
                msvcrt.locking(lf.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.05)
    else:
        import fcntl
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)


def _release_lock(lf) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            lf.seek(0)
            msvcrt.locking(lf.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def main() -> int:
    lock_path = pathlib.Path(tempfile.gettempdir()) / "na8ve-zig.lock"
    with open(lock_path, "a+b") as lf:
        if lock_path.stat().st_size == 0:
            lf.write(b"\0")
            lf.flush()
        _acquire_lock(lf)
        try:
            return subprocess.run([ZIG, *sys.argv[1:]]).returncode
        finally:
            _release_lock(lf)


if __name__ == "__main__":
    sys.exit(main())
