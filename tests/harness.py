# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal test harness for headless Blender runs.

Not built on ``unittest`` so the output stays greppable from a shell:
each check prints ``TEST:PASS:<name>`` or ``TEST:FAIL:<name>:<detail>`` and
the run ends with ``TEST:SUMMARY:<passed>/<total>``. The process exit code is
non-zero if anything failed, so CI / a shell one-liner can gate on it.
"""
from __future__ import annotations

import sys
import traceback

_results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> bool:
    _results.append((name, bool(condition), detail))
    tag = "PASS" if condition else "FAIL"
    line = f"TEST:{tag}:{name}"
    if detail and not condition:
        line += f":{detail}"
    print(line, flush=True)
    return bool(condition)


def eq(name: str, got, want) -> bool:
    return check(name, got == want, f"got {got!r} want {want!r}")


def run(test_funcs) -> int:
    """Run each zero-arg test function; return an exit code (0 = all pass)."""
    for fn in test_funcs:
        try:
            fn()
        except Exception:  # noqa: BLE001 -- a crashing test is a failed test
            check(f"{fn.__name__}:exception", False,
                  traceback.format_exc().replace("\n", " | "))

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print(f"TEST:SUMMARY:{passed}/{total}", flush=True)
    return 0 if passed == total else 1


def finish_and_exit(test_funcs) -> None:
    """Convenience: run and hard-exit Blender with the right code."""
    sys.exit(run(test_funcs))
