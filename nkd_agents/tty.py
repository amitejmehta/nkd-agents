"""Zero-abstraction line editor. termios + raw stdin, no event loop of its own.

Design choices that carry the weight; don't undo them without reading this.

1. The box lives in the bottom rows, *outside* the scroll region (DECSTBM), so any
   output (logging, print(), streamed tokens) scrolls above it with no coordination.
   The alternative (prompt_toolkit's patch_stdout: erase, print, redraw) breaks on one
   stray print(). Cost: the real cursor is hidden and a reverse-video fake is drawn.

2. A bracketed paste is one unit from Keys, appended to `buf` with newlines
   normalized to "\n" and other control characters dropped (they would reach the
   terminal raw and break the one-cell-per-char width assumption).

3. The box owns *color* and paints with autowrap off, so a row wider than the terminal
   (a long toolbar, wide CJK/emoji characters counted as one cell) is clipped by the
   terminal instead of wrapping; a row that wraps on the bottom row would scroll the
   screen and eat a line of output. `toolbar` is plain text painted in `style`. Sizing
   is re-derived from one os.get_terminal_size() per paint; SIGWINCH repaints, because
   a resize changes cols, height, box rows and DECSTBM at once. A resize ends the
   current output line: the cursor is re-parked at column 1 above the box, so a line
   streamed mid-way is split. Knowing the true row needs a cursor query (ESC[6n).

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
PASTE = "\x00"  # prefix on the key returned by Keys for a bracketed paste
DIM, RESET = "\x1b[38;5;242m", "\x1b[0m"  # grey 242
REV = "\x1b[7m"  # reverse video, drawn as the fake cursor
HIDE_CURSOR, SHOW_CURSOR = "\x1b[?25l", "\x1b[?25h"
PASTE_ON, PASTE_OFF = "\x1b[?2004h", "\x1b[?2004l"
PASTE_END = "\x1b[201~"
SAVE_CURSOR, RESTORE_CURSOR = "\x1b7", "\x1b8"
RESET_SCROLL_REGION = "\x1b[r"
CLEAR_TO_END = "\x1b[J"
WRAP_OFF, WRAP_ON = "\x1b[?7l", "\x1b[?7h"
IND = "\x1bD"  # scroll down one row, no carriage return (see Screen.paint)


def goto(row: int) -> str:
    return f"\x1b[{row};1H"


def clear_row(row: int) -> str:
    return f"{goto(row)}\x1b[2K"


def scroll_region(bottom: int) -> str:
    return f"\x1b[1;{bottom}r"


def up(rows: int) -> str:
    return f"\x1b[{rows}A" if rows else ""


class Keys:
    """Bytes on `fd` -> one key per read(). Knows nothing about the screen."""

    def __init__(self, fd: int = 0) -> None:
        self.fd = fd
        self._pending = ""  # input read past a paste terminator, not yet consumed
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

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

    async def read(self) -> str:
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
        while PASTE_END not in pasted:
            await self._fill()
            pasted, self._pending = pasted + self._pending, ""
        pasted, _, self._pending = pasted.partition(PASTE_END)
        return PASTE + pasted


@contextlib.contextmanager
def raw(fd: int) -> Iterator[None]:
    old = termios.tcgetattr(fd)
    tty.setcbreak(fd)  # no echo, no line buffering
    mode = termios.tcgetattr(fd)
    mode[0] &= ~termios.ICRNL  # don't translate \r -> \n, so enter != ctrl-j
    termios.tcsetattr(fd, termios.TCSADRAIN, mode)
    try:
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


class Screen:
    """The pinned rows at the bottom of the terminal.

    draw(cols) -> the rows to pin, already styled. Screen owns where they go (scroll
    region, room, resize) and nothing about what they say.
    """

    def __init__(self, draw: Callable[[int], list[str]], fd: int = 0) -> None:
        self.draw = draw
        self.fd = fd
        self.rows = 0
        self.active = False

    def write(self, s: str) -> None:
        sys.stdout.write(s)
        sys.stdout.flush()

    def paint(self, resized: bool = False) -> None:
        if not self.active:
            return
        cols, height = os.get_terminal_size()
        # The box never claims row 1, so the scroll region (rows 1..top-1) is always
        # at least one row tall and every index below lands on the screen. The slice
        # is the last resort for a terminal too short to hold even the chrome.
        box = self.draw(cols)[: max(0, height - 1)]
        top = height - len(box) + 1
        if resized:
            # A resize moves the cursor, so room cannot be made relative to it -
            # the indexes would fire at the bottom row and scroll output away,
            # a line per row of box. \x1b[J erases the re-wrapped box (always below
            # the cursor), then anchor absolutely above the box instead.
            self.write(CLEAR_TO_END + RESET_SCROLL_REGION + goto(top - 1))
        else:
            self.write(
                SAVE_CURSOR
                + RESET_SCROLL_REGION
                + RESTORE_CURSOR
                + IND * len(box)
                + up(len(box))
            )
        self.rows = len(box)
        self.write(
            SAVE_CURSOR
            + WRAP_OFF
            + scroll_region(top - 1)
            + "".join(f"{clear_row(i)}{line}" for i, line in enumerate(box, top))
            + WRAP_ON
            + RESTORE_CURSOR
        )

    def _clear(self) -> str:
        if not self.rows:
            return RESET_SCROLL_REGION
        top = os.get_terminal_size().lines - self.rows + 1
        return RESET_SCROLL_REGION + goto(top) + CLEAR_TO_END

    @contextlib.contextmanager
    def open(self) -> Iterator["Screen"]:
        with raw(self.fd):
            self.write(HIDE_CURSOR + PASTE_ON)
            # A resize invalidates cols, height, the box's row count and DECSTBM all
            # at once; only a repaint re-derives them from one consistent reading.
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGWINCH, self.paint, True)
            self.active = True
            try:
                self.paint()
                yield self
            finally:
                self.active = False
                loop.remove_signal_handler(signal.SIGWINCH)
                self.write(
                    PASTE_OFF
                    + SAVE_CURSOR
                    + self._clear()
                    + RESTORE_CURSOR
                    + SHOW_CURSOR
                )
                self.rows = 0


class Prompt:
    """Async prompt with key bindings, raw terminal only.

    key_bindings: raw key sequence (e.g. "\\x0c" for ctrl-l, ESC + "[Z" for
      shift-tab) -> sync callable(prompt) -> None. Ctrl-c, paste and ctrl-d on an
      empty line cannot be overridden.
    toolbar: optional callable() -> str, plain text rendered below the input box.
    style: color for the border, toolbar and the echoed submission, so your lines
      read apart from the output. Toolbar carries no escapes of its own: the box
      owns color.
    """

    def __init__(
        self,
        key_bindings: dict[str, Callable[["Prompt"], None]] | None = None,
        toolbar: Callable[[], str] | None = None,
        style: str = DIM,
        fd: int = 0,
    ) -> None:
        self.key_bindings = key_bindings or {}
        self.toolbar = toolbar or (lambda: "")
        self.style = style
        self.label = ""
        self.buf = ""
        self.keys = Keys(fd)
        self.screen = Screen(self.lines, fd)

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

    def _input_row(self, cols: int) -> str:
        text = (self.label + self.buf).replace("\n", " ")
        r = text[max(0, len(text) + 1 - cols) :]
        # REV = reverse video on, \x1b[27m = off: a 1-cell fake cursor
        return f"{r}{REV} \x1b[27m"

    def lines(self, cols: int) -> list[str]:
        def chrome(s: str) -> str:
            return self.style + s.replace("\n", " ") + RESET

        rule = chrome("─" * cols)
        return [rule, self._input_row(cols), rule, chrome(self.toolbar())]

    async def prompt_async(self, label: str = "❯ ") -> str:
        self.buf, self.label = "", label
        with self.screen.open():
            while (key := await self.keys.read()) != "\r":
                self._handle(key)
                self.screen.paint()
        self.screen.write(f"\n{self.style}{label}{self.buf}{RESET}\n\n")
        return self.buf
