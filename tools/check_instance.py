"""Verify duplicate launches connect to the owned, empty test instance on Windows."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from ctypes import wintypes


def check(executable, report):
    result = {}
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    with tempfile.TemporaryDirectory(prefix="sori-instance-check-") as directory:
        environment = os.environ.copy()
        environment.pop("QT_QPA_PLATFORM", None)
        first = subprocess.Popen([str(executable), "--data-dir", directory], env=environment)
        try:
            def windows():
                found = []
                @callback_type
                def visit(hwnd, unused):
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    if pid.value == first.pid and user32.IsWindowVisible(hwnd):
                        found.append(hwnd)
                    return True
                user32.EnumWindows(visit, 0)
                return found
            until = time.monotonic() + 20
            while not windows() and time.monotonic() < until:
                if first.poll() is not None:
                    raise RuntimeError("First instance exited during startup")
                time.sleep(0.1)
            if not windows():
                raise RuntimeError("Owned first-run setup window did not appear")
            second = subprocess.run([str(executable), "--data-dir", directory, "--dashboard"],
                                    env=environment, timeout=20)
            result.update(duplicate_exit_code=second.returncode, original_running=first.poll() is None,
                          setup_windows=len(windows()))
            result["ok"] = second.returncode == 0 and result["original_running"] and result["setup_windows"] == 1
        except Exception as exc:
            result.update(ok=False, error=str(exc))
        finally:
            # Only our empty, temporary test instance is terminated.
            if first.poll() is None:
                first.terminate()
                first.wait(timeout=10)
    report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    raise SystemExit(check(args.executable, args.report))
