#!/usr/bin/env python3
"""Break each invariant in tty.py on purpose and check a test notices.

A passing suite proves nothing until you know it can fail. Every entry below is an
invariant we actually rely on; if a mutant survives, the tests are decorative and
the next refactor will silently break that invariant.

    python scripts/tty_mutants.py            # all of them
    python scripts/tty_mutants.py --list     # just the names

Not part of `pytest`: this spawns pytest per mutant, so nesting it in the suite
would make it recursive and slow. Run it before a refactor of tty.py, or in CI.
"""

import argparse
import subprocess
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "nkd_agents" / "tty.py"
TESTS = ["tests/test_tty.py", "tests/test_tty_screen.py"]

# (name, original source, replacement). Each must break exactly one invariant.
MUTANTS: list[tuple[str, str, str]] = [
    (
        "no clipping of chrome to the terminal width",
        'return self.style + s.replace("\\n", " ")[:cols] + RESET',
        "return self.style + s + RESET",
    ),
    (
        "no newline strip (a newline is a second row)",
        'return self.style + s.replace("\\n", " ")[:cols] + RESET',
        "return self.style + s[:cols] + RESET",
    ),
    ("no room made for the box", "self._room(len(box))", "self._rows = len(box)"),
    (
        "no clearing of rows freed by a shrink",
        "blanks = max(0, min(top - 1, self._rows - len(box)))",
        "blanks = 0",
    ),
    (
        "no scroll region",
        "SAVE_CURSOR\n            + scroll_region(top - 1)",
        'SAVE_CURSOR\n            + ""',
    ),
    (
        "box may claim row 1 (negative row escapes)",
        "[rule, *self._input_rows(cols), rule, chrome(self.toolbar())][\n            : max(0, height - 1)\n        ]",
        "[rule, *self._input_rows(cols), rule, chrome(self.toolbar())]",
    ),
    ("no zero-width guard", "cols = max(1, cols)", "pass"),
    (
        "resize does not erase the reflowed box",
        "CLEAR_TO_END + RESET_SCROLL_REGION + goto(top - 1)",
        "RESET_SCROLL_REGION + goto(top - 1)",
    ),
    (
        "resize makes room relative to the moved cursor",
        "self._write(CLEAR_TO_END + RESET_SCROLL_REGION + goto(top - 1))\n            "
        "self._rows = len(box)",
        "self._write(CLEAR_TO_END)\n            self._room(len(box))",
    ),
    (
        "resize does not anchor the cursor above the box",
        "CLEAR_TO_END + RESET_SCROLL_REGION + goto(top - 1)",
        "CLEAR_TO_END + RESET_SCROLL_REGION",
    ),
    (
        "room does not restore the cursor",
        'return f"\\x1b[{rows}A" if rows else ""',
        'return ""',
    ),
    (
        "room indexes with a bare newline (CR+LF under ONLCR)",
        'IND = "\\x1bD"',
        'IND = "\\n"',
    ),
    (
        "room does not reset the previous render's scroll region",
        "SAVE_CURSOR + RESET_SCROLL_REGION + RESTORE_CURSOR + IND * rows",
        'SAVE_CURSOR + "" + RESTORE_CURSOR + IND * rows',
    ),
    (
        "room lets \\x1b[r home the cursor (real terminals do; pyte does not)",
        "SAVE_CURSOR + RESET_SCROLL_REGION + RESTORE_CURSOR + IND * rows",
        "RESET_SCROLL_REGION + IND * rows",
    ),
    (
        "second prompt reclaims the previous box's rows",
        "self._rows = 0  # the last box was erased at teardown; nothing to reclaim",
        "pass",
    ),
    (
        "echo lands on a writer's half-written line",
        'self._write(f"\\n{self.style}{label}',
        'self._write(f"{self.style}{label}',
    ),
    (
        "echo is not styled",
        'self._write(f"\\n{self.style}{label}',
        'self._write(f"\\n{label}',
    ),
    (
        "no SIGWINCH handler",
        "loop.add_signal_handler(signal.SIGWINCH, self._render, True)",
        "pass",
    ),
]


def killed(source: str, original: str, replacement: str) -> bool:
    """True if the suite fails once `original` is replaced. Restores the file."""
    if original not in source:
        raise SystemExit(f"mutant no longer applies, source changed: {original!r}")
    TARGET.write_text(source.replace(original, replacement, 1))
    try:
        run = subprocess.run(
            [sys.executable, "-m", "pytest", *TESTS, "-q", "-x", "--no-header"],
            capture_output=True,
        )
        return run.returncode != 0
    finally:
        TARGET.write_text(source)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print names and exit")
    args = ap.parse_args()
    if args.list:
        print("\n".join(name for name, _, _ in MUTANTS))
        return 0

    source = TARGET.read_text()
    survivors = []
    for name, original, replacement in MUTANTS:
        ok = killed(source, original, replacement)
        print(f"  {'killed ' if ok else 'SURVIVED'}  {name}", flush=True)
        if not ok:
            survivors.append(name)

    print(f"\n{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} killed")
    for name in survivors:
        print(f"  survivor: {name} - no test covers this invariant")
    return 1 if survivors else 0


if __name__ == "__main__":
    raise SystemExit(main())
