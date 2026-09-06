"""Zero-abstraction line editor. termios + raw stdin, no event loop of its own.

Three design choices carry most of the weight; don't undo them without reading this.

1. The input box lives in the bottom rows, *outside* the terminal's scroll region
   (DECSTBM). Output printed anywhere - logging, print(), streamed tokens - scrolls
   above it with zero coordination. The alternative (prompt_toolkit's patch_stdout:
   erase box, print, redraw) requires every writer to go through the prompt; one
   stray print() breaks it. Cost: the real cursor is hidden in the output area and
   a reverse-video fake cursor is drawn in the box (see _render).

2. A bracketed paste is stored as ONE private-use char (chr(PUA+n)) in `buf`, shown
   as `[Paste #n, k lines]`, expanded on submit. Movement/deletion is atomic by
   construction, so no code defends the placeholder. An earlier version stored the
   label text in `buf` and needed regexes everywhere to keep it intact.

3. The box owns *width* and *color*. `toolbar` and `border` are plain text painted in
   `style`; every chrome row is cut to the terminal width. A row that overflows
   wraps, and wrapping on the bottom row scrolls the whole screen - which walks the
   box upward and eats a line of real output.

Sizing is re-derived from one `os.get_terminal_size()` per render, and a SIGWINCH
handler repaints: a resize changes cols, height, the box's row count and DECSTBM all
at once, and the terminal re-wraps the old box into the scroll region.

Also: input wraps and the box grows, but buf is always one logical line; Enter
always submits. No history (removed: unused), no completion, no vi mode.

tests/test_tty.py pins every key and the escapes; tests/test_tty_screen.py drives a
VT emulator and asserts what lands on screen; scripts/tty_mutants.py breaks each
invariant here on purpose and checks a test notices. Run it before refactoring.
"""

import asyncio
import contextlib
import os
import re
import signal
import sys
import termios
import tty
from collections.abc import Callable, Iterator

ESC = "\x1b"
PASTE = "\x00"  # prefix on the key returned by _read_key for a bracketed paste
PUA = 0xE000  # paste n is stored in buf as chr(PUA + n)
CHROME = 3  # rule above, rule below, toolbar
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


# key -> (direction, by_word). Backspace deletes left; delete / option-delete right.
DELETES = {
    "\x7f": (-1, False),  # backspace
    "\x08": (-1, False),  # backspace (ctrl-h terminals)
    ESC + "\x7f": (-1, True),  # option-backspace
    ESC + "\x08": (-1, True),  # option-backspace (ctrl-h terminals)
    "\x17": (-1, True),  # ctrl-w
    ESC + "[3~": (1, False),  # delete
    ESC + "d": (1, True),  # option-delete (emacs)
    ESC + "[3;3~": (1, True),  # option-delete (xterm)
}
# key -> (direction, by_word). Option/alt-arrows: emacs, xterm, and ctrl variants.
MOVES = {
    ESC + "[D": (-1, False),  # left
    ESC + "[C": (1, False),  # right
    ESC + "b": (-1, True),  # option-left (emacs)
    ESC + "f": (1, True),  # option-right (emacs)
    ESC + "[1;3D": (-1, True),  # option-left (xterm)
    ESC + "[1;3C": (1, True),  # option-right (xterm)
    ESC + "[1;5D": (-1, True),  # ctrl-left
    ESC + "[1;5C": (1, True),  # ctrl-right
}


class Prompt:
    """Async prompt with key bindings, raw terminal only.

    key_bindings: raw key sequence (e.g. "\\x0c" for ctrl-l, ESC + "[Z" for
      shift-tab) -> sync callable(prompt) -> None. Built-in editing keys, ctrl-c
      and ctrl-d cannot be overridden.
    toolbar: optional callable() -> str, plain text rendered below the input box.
    border: character repeated to draw the rules above and below the input.
    style: color for the border, toolbar and the echoed submission, so your lines
      read apart from the output. Toolbar and border carry no escapes of their own:
      the box owns color as well as width, and cuts every chrome row to the latter.
    """

    def __init__(
        self,
        key_bindings: dict[str, Callable[["Prompt"], None]] | None = None,
        toolbar: Callable[[], str] | None = None,
        border: str = "─",
        style: str = DIM,
    ) -> None:
        self.key_bindings = key_bindings or {}
        self.toolbar = toolbar or (lambda: "")
        self.border = border
        self.style = style
        self.label = ""
        self.buf = ""
        self.cursor = 0
        self.pastes: list[str] = []
        self.fd = 0  # stdin
        self._pending = ""  # input read past a paste terminator, not yet consumed
        self._rows = 0

    # -- editing (pure) -----------------------------------------------------

    def _insert(self, text: str) -> None:
        self.buf = self.buf[: self.cursor] + text + self.buf[self.cursor :]
        self.cursor += len(text)

    def _paste(self, text: str) -> None:
        self.pastes.append(text.replace("\r\n", "\n").replace("\r", "\n"))
        self._insert(chr(PUA + len(self.pastes) - 1))

    def _paste_idx(self, c: str) -> int | None:
        n = ord(c) - PUA
        return n if 0 <= n < len(self.pastes) else None

    def _label(self, n: int) -> str:
        lines = self.pastes[n].rstrip("\n").count("\n") + 1
        return f"[Paste #{n + 1}, {lines} line{'s' * (lines > 1)}]"

    def _display(self, s: str) -> str:
        """`s` with each paste character replaced by its `[Paste #n, k lines]` label."""
        return "".join(
            c if (n := self._paste_idx(c)) is None else self._label(n) for c in s
        )

    def _expand(self) -> str:
        """Buffer with paste characters replaced by their pasted text."""
        return "".join(
            c if (n := self._paste_idx(c)) is None else self.pastes[n] for c in self.buf
        )

    def _seek(self, direction: int, word: bool) -> int:
        """Cursor position after moving one char or one word."""
        if not word:
            return max(0, min(len(self.buf), self.cursor + direction))
        if direction < 0:
            m = re.search(r"\S+\s*$", self.buf[: self.cursor])
            return m.start() if m else 0
        m = re.match(r"\s*\S+", self.buf[self.cursor :])
        return self.cursor + m.end() if m else len(self.buf)

    def _delete(self, direction: int, word: bool) -> None:
        lo, hi = sorted((self.cursor, self._seek(direction, word)))
        self.buf = self.buf[:lo] + self.buf[hi:]
        self.cursor = lo

    def _handle(self, key: str) -> None:
        if key.startswith(PASTE):
            self._paste(key[1:])
        elif dele := DELETES.get(key):
            self._delete(*dele)
        elif move := MOVES.get(key):
            self.cursor = self._seek(*move)
        elif key == "\x03":  # ctrl-c
            raise KeyboardInterrupt
        elif key == "\x04" and not self.buf:  # ctrl-d on empty line
            raise EOFError
        elif fn := self.key_bindings.get(key):
            fn(self)
        elif key.isprintable():
            self._insert(key)

    # -- rendering ----------------------------------------------------------

    def _write(self, s: str) -> None:
        sys.stdout.write(s)
        sys.stdout.flush()

    def _input_rows(self, cols: int) -> list[str]:
        """Wrap label+buf into terminal rows, with a reverse-video fake cursor."""
        text = self.label + self._display(self.buf)
        offset = len(self.label) + len(self._display(self.buf[: self.cursor]))
        rows = [text[j : j + cols] for j in range(0, len(text) + 1, cols)]
        cur_row, cur_col = offset // cols, offset % cols
        r, c = rows[cur_row], cur_col
        # REV = reverse video on, \x1b[27m = off: a 1-cell fake cursor
        rows[cur_row] = f"{r[:c]}{REV}{r[c : c + 1] or ' '}\x1b[27m{r[c + 1 :]}"
        return rows

    def _room(self, rows: int) -> None:
        """Put `rows` empty rows below the cursor, leaving the cursor where it was.

        The only way space is ever made. Idempotent: once the cursor is `rows` from
        the bottom the indexes just walk down and back; if the box grew, the last
        ones scroll output up by exactly the shortfall. \\x1b[r first, or they would
        scroll inside the previous render's region. \\x1b[0A would move 1, not 0.

        Two things real terminals do that pyte does not, so no screen test can catch
        either; tests/test_tty.py pins the exact bytes instead:
        - DECSTBM (\\x1b[r, with or without params) homes the cursor to (1,1). Without
          the \\x1b7/\\x1b8 around it the cursor would end up at the top of the screen
          and every print() after this render would overwrite output from row 1.
        - The tty layer still has OPOST|ONLCR on, so a "\\n" would go out as CR+LF
          and move the cursor to column 1, truncating any output line written without
          a trailing newline. \\x1bD (IND) scrolls the same but never carriage-returns.
        """
        self._write(
            SAVE_CURSOR + RESET_SCROLL_REGION + RESTORE_CURSOR + IND * rows + up(rows)
        )
        self._rows = rows

    def _layout(self, cols: int, height: int) -> tuple[list[str], int]:
        """Box rows and the 1-based screen row they start on. Pure: no I/O."""

        def chrome(s: str) -> str:
            return self.style + s.replace("\n", " ")[:cols] + RESET

        # The box never claims row 1, so the scroll region (rows 1..top-1) is always
        # at least one row tall and every index below lands on the screen. The slice
        # is the last resort for a terminal too short to hold even the chrome.
        rule = chrome(self.border * cols)
        box = [rule, *self._input_rows(cols), rule, chrome(self.toolbar())][
            : max(0, height - 1)
        ]
        return box, height - len(box) + 1

    def _render(self, resized: bool = False) -> None:
        cols, height = os.get_terminal_size()
        cols = max(1, cols)  # a zero-width terminal would divide by zero below
        box, top = self._layout(cols, height)
        # Rows a shrink freed above the box are still ours, and get painted blank.
        blanks = max(0, min(top - 1, self._rows - len(box)))
        if resized:
            # A resize moves the cursor, so room cannot be made relative to it -
            # _room's indexes would fire at the bottom row and scroll output away,
            # a line per row of box. \x1b[J erases the re-wrapped box (always below
            # the cursor), then anchor absolutely above the box instead.
            self._write(CLEAR_TO_END + RESET_SCROLL_REGION + goto(top - 1))
            self._rows = len(box)
        else:
            self._room(len(box))
        painted = enumerate([""] * blanks + box, start=top - blanks)
        self._write(
            SAVE_CURSOR
            + scroll_region(top - 1)
            + "".join(f"{clear_row(i)}{line}" for i, line in painted)
            + RESTORE_CURSOR
        )

    # -- input --------------------------------------------------------------

    async def _fill(self) -> None:
        """Wait for stdin, then append everything it has to `_pending`.

        add_reader, not run_in_executor: a worker thread blocked in os.read cannot
        be cancelled, and the default executor joins its threads at exit, so ctrl-c
        would hang until a second one. A reader is just removed.
        """
        loop = asyncio.get_running_loop()
        readable = loop.create_future()
        loop.add_reader(self.fd, readable.set_result, None)
        try:
            await readable
        finally:
            loop.remove_reader(self.fd)
        self._pending += os.read(self.fd, 4096).decode(errors="replace")

    async def _read_key(self) -> str:
        if not self._pending:
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
        """cbreak mode, enter as \\r (ICRNL off), hidden cursor, bracketed paste."""
        old = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)  # no echo, no line buffering; ctrl-c still a keystroke
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
        """The submitted line, expanded. Echoed on a line of its own: the leading
        "\\n" ends whatever a concurrent writer left half-written."""
        self.buf, self.cursor, self.pastes, self.label = "", 0, [], label
        self._rows = 0  # the last box was erased at teardown; nothing to reclaim
        with self._raw():
            self._render()
            while (key := await self._read_key()) != "\r":
                self._handle(key)
                self._render()
        self._write(f"\n{self.style}{label}{self._display(self.buf)}{RESET}\n\n")
        return self._expand()
