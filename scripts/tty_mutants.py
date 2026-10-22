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
        "autowrap stays on while painting (wide or long rows scroll the screen)",
        "            + WRAP_OFF\n",
        "",
    ),
    (
        "no newline strip (a newline is a second row)",
        'return self.style + s.replace("\\n", " ") + RESET',
        "return self.style + s + RESET",
    ),
    (
        "no room made for the box",
        "+ IND * len(box)\n                + up(len(box))",
        "",
    ),
    (
        "no scroll region",
        "+ scroll_region(top - 1)\n",
        "\n",
    ),
    (
        "box may claim row 1 (negative row escapes)",
        "self.draw(cols)[: max(0, height - 1)]",
        "self.draw(cols)",
    ),
    (
        "resize does not erase the reflowed box",
        "self.write(CLEAR_TO_END + RESET_SCROLL_REGION + goto(top - 1))",
        "self.write(RESET_SCROLL_REGION + goto(top - 1))",
    ),
    (
        "resize makes room relative to the moved cursor",
        "self.write(CLEAR_TO_END + RESET_SCROLL_REGION + goto(top - 1))",
        "self.write(CLEAR_TO_END + IND * len(box) + up(len(box)))",
    ),
    (
        "resize does not anchor the cursor above the box",
        "self.write(CLEAR_TO_END + RESET_SCROLL_REGION + goto(top - 1))",
        "self.write(CLEAR_TO_END + RESET_SCROLL_REGION)",
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
        "SAVE_CURSOR\n                + RESET_SCROLL_REGION\n                + RESTORE_CURSOR",
        "SAVE_CURSOR\n                + RESTORE_CURSOR",
    ),
    (
        "room lets \\x1b[r home the cursor (real terminals do; pyte does not)",
        "SAVE_CURSOR\n                + RESET_SCROLL_REGION\n                + RESTORE_CURSOR",
        "RESET_SCROLL_REGION",
    ),
    (
        "teardown clears the bottom row when nothing was painted",
        "        if not self.rows:\n            return RESET_SCROLL_REGION\n",
        "",
    ),
    (
        "echo lands on a writer's half-written line",
        'self.screen.write(f"\\n{self.style}{label}',
        'self.screen.write(f"{self.style}{label}',
    ),
    (
        "echo is not styled",
        'self.screen.write(f"\\n{self.style}{label}',
        'self.screen.write(f"\\n{label}',
    ),
    (
        "no SIGWINCH handler",
        "loop.add_signal_handler(signal.SIGWINCH, self.paint, True)",
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
