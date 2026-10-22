"""Zero-abstraction line editor. termios + raw stdin, no event loop of its own.

Design choices that carry the weight; don't undo them without reading this.

1. The box lives in the bottom rows, *outside* the scroll region (DECSTBM), so any
   output (logging, print(), streamed tokens) scrolls above it with no coordination.
   The alternative (prompt_toolkit's patch_stdout: erase, print, redraw) breaks on one
   stray print(). Cost: the real cursor is hidden and a reverse-video fake is drawn.

2. A bracketed paste is one unit from _read_key, appended to `buf` with newlines
   normalized to "\n" and other control characters dropped (they would reach the
   terminal raw and break the one-cell-per-char width assumption).

3. The box owns *width* and *color*. `toolbar` is plain text painted in `style`; every
   chrome row is cut to the terminal width, since a row that wraps on the bottom row
   scrolls the screen and eats a line of output. Sizing is re-derived from one
   os.get_terminal_size() per render; SIGWINCH repaints, because a resize changes
   cols, height, box rows and DECSTBM at once.

4. Editing is tail-only: the cursor is pinned to the end of buf, so typing and pasting
   append and nothing mid-line is editable. Input is one row scrolling horizontally,
   so the box has constant height; newlines in buf display as spaces.

Keys with built-in behavior: printable chars append; Enter submits; Ctrl-C is SIGINT
(ISIG stays on), surfacing as KeyboardInterrupt; Ctrl-D on an empty line raises EOFError; a paste appends. Everything
else (backspace, arrows, Tab, ESC, Ctrl-W...) is a silent no-op until bound in
key_bindings, whose callbacks may mutate `prompt.buf`.

One os.read is one key, matched whole against key_bindings. A keypress is one terminal
write, so multi-byte keys (Shift+Tab = ESC [ Z) arrive together and match their full
string; separate presses are separate reads, so an ESC-prefixed chord can't be typed
by hand. A bare-ESC binding doesn't shadow ESC-prefixed ones.

Known limitation, intentional: a typed ESC and the next keystroke landing in one read
(SSH stall batching) glue into one key. Unbound, it is dropped (press ESC again); if an
ESC-prefixed binding matches (e.g. "\\x1bx") it fires, indistinguishable from Alt+x.
Fixing it needs timing or a keyboard protocol (kitty, modifyOtherKeys), both out of
scope. Don't bind destructive actions to ESC+key.

tests/test_tty.py pins every key and the escapes; tests/test_tty_screen.py drives a
VT emulator and asserts what lands on screen; scripts/tty_mutants.py breaks each
invariant here on purpose and checks a test notices. Run it before refactoring.
"""

import asyncio
import codecs
import contextlib
import os
import signal
import sys
import termios
import tty
from collections.abc import Callable, Iterator

ESC = "\x1b"
PASTE = "\x00"  # prefix on the key returned by _read_key for a bracketed paste
DIM, RESET = "\x1b[38;5;242m", "\x1b[0m"  # grey 242
REV = "\x1b[7m"  # reverse video, drawn as the fake cursor
HIDE_CURSOR, SHOW_CURSOR = "\x1b[?25l", "\x1b[?25h"
PASTE_ON, PASTE_OFF = "\x1b[?2004h", "\x1b[?2004l"
SAVE_CURSOR, RESTORE_CURSOR = "\x1b7", "\x1b8"
RESET_SCROLL_REGION = "\x1b[r"
CLEAR_TO_END = "\x1b[J"
IND = "\x1bD"  # scroll down one row, no carriage return (see _room)


def goto(row: int) -> str:
    return f"\x1b[{row};1H"


def clear_row(row: int) -> str:
    return f"{goto(row)}\x1b[2K"


def scroll_region(bottom: int) -> str:
    return f"\x1b[1;{bottom}r"


def up(rows: int) -> str:
    return f"\x1b[{rows}A" if rows else ""


class Prompt:
    """Async prompt with key bindings, raw terminal only.

    key_bindings: raw key sequence (e.g. "\\x0c" for ctrl-l, ESC + "[Z" for
      shift-tab) -> sync callable(prompt) -> None. Ctrl-c, paste and ctrl-d on an
      empty line cannot be overridden.
    toolbar: optional callable() -> str, plain text rendered below the input box.
    style: color for the border, toolbar and the echoed submission, so your lines
      read apart from the output. Toolbar carries no escapes of its own: the box
      owns color as well as width, and cuts every chrome row to the latter.
    """

    def __init__(
        self,
        key_bindings: dict[str, Callable[["Prompt"], None]] | None = None,
        toolbar: Callable[[], str] | None = None,
        style: str = DIM,
    ) -> None:
        self.key_bindings = key_bindings or {}
        self.toolbar = toolbar or (lambda: "")
        self.style = style
        self.label = ""
        self.buf = ""
        self.fd = 0  # stdin
        self._pending = ""  # input read past a paste terminator, not yet consumed
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._rows = 0
        self._active = False

    def refresh(self) -> None:
        if self._active:
            self._render()

    # -- editing (pure) -----------------------------------------------------

    def _handle(self, key: str) -> None:
        if key.startswith(PASTE):
            text = key[1:].replace("\r\n", "\n").replace("\r", "\n")
            self.buf += "".join(c for c in text if c.isprintable() or c == "\n")
        elif key == "\x04" and not self.buf:  # ctrl-d on empty line
            raise EOFError
        elif fn := self.key_bindings.get(key):
            fn(self)
        elif key.isprintable():
            self.buf += key

    # -- rendering ----------------------------------------------------------

    def _write(self, s: str) -> None:
        sys.stdout.write(s)
        sys.stdout.flush()

    def _input_row(self, cols: int) -> str:
        text = (self.label + self.buf).replace("\n", " ")
        r = text[max(0, len(text) + 1 - cols) :]
        # REV = reverse video on, \x1b[27m = off: a 1-cell fake cursor
        return f"{r}{REV} \x1b[27m"

    def _room(self, rows: int) -> None:
        self._write(
            SAVE_CURSOR + RESET_SCROLL_REGION + RESTORE_CURSOR + IND * rows + up(rows)
        )

    def _layout(self, cols: int, height: int) -> tuple[list[str], int]:
        def chrome(s: str) -> str:
            return self.style + s.replace("\n", " ")[:cols] + RESET

        # The box never claims row 1, so the scroll region (rows 1..top-1) is always
        # at least one row tall and every index below lands on the screen. The slice
        # is the last resort for a terminal too short to hold even the chrome.
        rule = chrome("─" * cols)
        box = [rule, self._input_row(cols), rule, chrome(self.toolbar())][
            : max(0, height - 1)
        ]
        return box, height - len(box) + 1

    def _render(self, resized: bool = False) -> None:
        cols, height = os.get_terminal_size()
        box, top = self._layout(cols, height)
        if resized:
            # A resize moves the cursor, so room cannot be made relative to it -
            # _room's indexes would fire at the bottom row and scroll output away,
            # a line per row of box. \x1b[J erases the re-wrapped box (always below
            # the cursor), then anchor absolutely above the box instead.
            self._write(CLEAR_TO_END + RESET_SCROLL_REGION + goto(top - 1))
        else:
            self._room(len(box))
        self._rows = len(box)
        self._write(
            SAVE_CURSOR
            + scroll_region(top - 1)
            + "".join(f"{clear_row(i)}{line}" for i, line in enumerate(box, top))
            + RESTORE_CURSOR
        )

    # -- input --------------------------------------------------------------

    async def _fill(self) -> None:
        loop = asyncio.get_running_loop()
        readable = loop.create_future()
        loop.add_reader(self.fd, readable.set_result, None)
        try:
            await readable
        finally:
            loop.remove_reader(self.fd)
        if not (data := os.read(self.fd, 4096)):
            raise EOFError
        self._pending += self._decoder.decode(data)

    async def _read_key(self) -> str:
        while not self._pending:
            await self._fill()
        ch, self._pending = self._pending[0], self._pending[1:]
        if ch != ESC:
            return ch
        # ESC alone vs. the start of a sequence (arrows, alt-keys, paste): a terminal
        # sends a sequence in one write, so it is whatever arrived with the ESC.
        # Empty -> bare escape key.
        rest, self._pending = self._pending, ""
        if not rest.startswith("[200~"):  # \x1b[200~ = bracketed paste start
            return ESC + rest
        pasted = rest.removeprefix("[200~")
        while ESC + "[201~" not in pasted:  # \x1b[201~ = bracketed paste end
            await self._fill()
            pasted, self._pending = pasted + self._pending, ""
        pasted, _, self._pending = pasted.partition(ESC + "[201~")
        return PASTE + pasted

    @contextlib.contextmanager
    def _raw(self) -> Iterator[None]:
        old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)  # no echo, no line buffering
        mode = termios.tcgetattr(self.fd)
        mode[0] &= ~termios.ICRNL  # don't translate \r -> \n, so enter != ctrl-j
        termios.tcsetattr(self.fd, termios.TCSADRAIN, mode)
        # The first _render makes its own room, so there is nothing to reserve here.
        self._write(HIDE_CURSOR + PASTE_ON)
        # A resize invalidates cols, height, the box's row count and DECSTBM all at
        # once; only a repaint re-derives them from one consistent reading.
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGWINCH, self._render, True)
        try:
            yield
        finally:
            loop.remove_signal_handler(signal.SIGWINCH)
            height = os.get_terminal_size().lines
            top = height - self._rows + 1
            self._write(
                PASTE_OFF
                + SAVE_CURSOR
                + RESET_SCROLL_REGION
                + goto(top)
                + CLEAR_TO_END
                + RESTORE_CURSOR
                + SHOW_CURSOR
            )
            termios.tcsetattr(self.fd, termios.TCSADRAIN, old)

    async def prompt_async(self, label: str = "❯ ") -> str:
        self.buf, self.label = "", label
        with self._raw():
            self._active = True
            try:
                self._render()
                while (key := await self._read_key()) != "\r":
                    self._handle(key)
                    self._render()
            finally:
                self._active = False
        self._write(f"\n{self.style}{label}{self.buf}{RESET}\n\n")
        return self.buf
