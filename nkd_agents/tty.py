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

3. The box owns *width*, the caller owns *color*. `toolbar`, `border` and `style` may
   carry any escapes; _clip cuts every chrome row to the terminal in cells, not
   characters. A row that overflows wraps, and wrapping on the bottom row scrolls the
   whole screen - which walks the box upward and eats a line of real output.

Sizing is re-derived from one `os.get_terminal_size()` per render, and a SIGWINCH
handler repaints: a resize changes cols, height, the box's row count and DECSTBM all
at once, and the terminal re-wraps the old box into the scroll region.

Also: input wraps and the box grows; ctrl-j / alt-enter / shift-enter insert a
newline (shift-enter needs a kitty-protocol terminal). No history (removed: unused),
no completion, no vi mode.

tests/test_tty.py pins every key and the escapes; tests/test_tty_screen.py drives a
VT emulator and asserts what lands on screen; scripts/tty_mutants.py breaks each
invariant here on purpose and checks a test notices. Run it before refactoring.
"""

import asyncio
import contextlib
import os
import re
import select
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
SGR = re.compile(r"(\x1b\[[0-9;]*m)")  # a color escape: some chars, zero cells
REV = "\x1b[7m"  # reverse video, drawn as the fake cursor
NEWLINE_KEYS = ("\n", ESC + "\r", ESC + "[13;2u")  # ctrl-j, alt-enter, shift-enter
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


def _clip(s: str, cols: int) -> str:
    """`s` as one row of at most `cols` *cells*, never cut mid-escape.

    Colors cost no budget, so `s[:cols]` under-fills and `cols + len(escapes)`
    overshoots by any escape past the cut; spend the budget while walking instead.
    """
    out, budget = "", cols
    for i, part in enumerate(SGR.split(s.replace("\n", " "))):
        if i % 2:  # odd parts are the capture group: an escape, kept whole and free
            out += part
        else:
            out += part[:budget]
            budget -= len(part[:budget])
    return out


class Prompt:
    """Async prompt with key bindings, raw terminal only.

    key_bindings: raw key sequence (e.g. "\\x0c" for ctrl-l, ESC + "[Z" for
      shift-tab) -> sync callable(prompt) -> None. Built-in editing keys, ctrl-c
      and ctrl-d cannot be overridden.
    toolbar: optional callable() -> str, rendered below the input box.
    border: character repeated to draw the rules above and below the input.
    style: default color for the border and toolbar. Either may carry its own
      escapes instead; the box only owns width, and cuts both to it (see _clip).
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
        self.pastes.append(text)
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
        elif key in NEWLINE_KEYS:
            self._insert("\n")
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
        rows: list[str] = []
        pad = " " * len(self.label)
        head = self.buf[: self.cursor]
        cur_line = head.count("\n")
        offset = len(self._display(head[head.rfind("\n") + 1 :])) + len(pad)
        cur_row = cur_col = 0
        for i, line in enumerate(self.buf.split("\n")):
            if i == cur_line:
                cur_row, cur_col = len(rows) + offset // cols, offset % cols
            text = (self.label if i == 0 else pad) + self._display(line)
            rows += [text[j : j + cols] for j in range(0, len(text) + 1, cols)]
        r, c = rows[cur_row], cur_col
        # REV = reverse video on, \x1b[27m = off: a 1-cell fake cursor
        rows[cur_row] = f"{r[:c]}{REV}{r[c : c + 1] or ' '}\x1b[27m{r[c + 1 :]}"
        return rows

    def _window(self, rows: list[str], limit: int) -> list[str]:
        """At most `limit` of `rows`, sliding to keep the cursor's row visible."""
        if len(rows) <= limit:
            return rows
        cur = next(i for i, r in enumerate(rows) if REV in r)
        start = min(max(0, cur - limit + 1), len(rows) - limit)
        return rows[start : start + limit]

    def _room(self, rows: int) -> None:
        """Put `rows` empty rows below the cursor, leaving the cursor where it was.

        The only way space is ever made. Idempotent: once the cursor is `rows` from
        the bottom the indexes just walk down and back; if the box grew, the last
        ones scroll output up by exactly the shortfall. \\x1b[r first, or they would
        scroll inside the previous render's region. \\x1b[0A would move 1, not 0.

        \\x1bD (IND) and not "\\n": the tty layer still has OPOST|ONLCR on, so a "\\n"
        would go out as CR+LF and move the cursor to column 1, truncating any output
        line written without a trailing newline. IND scrolls the same but never
        carriage-returns. pyte does not model ONLCR, so no test can catch this.
        """
        self._write("\x1b[r" + "\x1bD" * rows + (f"\x1b[{rows}A" if rows else ""))
        self._rows = rows

    def _render(self, resized: bool = False) -> None:
        cols, height = os.get_terminal_size()
        cols = max(1, cols)  # a zero-width terminal would divide by zero below

        def chrome(s: str) -> str:
            return _clip(self.style + s, cols) + RESET

        # The box never claims row 1, so the scroll region (rows 1..top-1) is always
        # at least one row tall and every index below lands on the screen. The window
        # enforces it for any usable terminal; the slice is the last resort for one
        # too short to hold even the chrome.
        rule = chrome(self.border * cols)
        rows = self._window(self._input_rows(cols), max(1, height - CHROME - 1))
        box = [rule, *rows, rule, chrome(self.toolbar())][: max(0, height - 1)]
        top = height - len(box) + 1
        # Rows a shrink freed above the box are still ours, and get painted blank.
        blanks = max(0, min(top - 1, self._rows - len(box)))
        if resized:
            # A resize moves the cursor, so room cannot be made relative to it -
            # _room's indexes would fire at the bottom row and scroll output away,
            # a line per row of box. \x1b[J erases the re-wrapped box (always below
            # the cursor), then anchor absolutely above the box instead.
            self._write(f"\x1b[J\x1b[r\x1b[{top - 1};1H")
            self._rows = len(box)
        else:
            self._room(len(box))
        # \x1b7 = save cursor, \x1b8 = restore it to the output area; \x1b[1;Nr =
        # scroll region rows 1..N; \x1b[i;1H = goto row i col 1; \x1b[2K = clear it.
        painted = enumerate([""] * blanks + box, start=top - blanks)
        self._write(
            f"\x1b7\x1b[1;{top - 1}r"
            + "".join(f"\x1b[{i};1H\x1b[2K{line}" for i, line in painted)
            + "\x1b8"
        )

    # -- input --------------------------------------------------------------

    def _read(self, n: int) -> str:
        return os.read(self.fd, n).decode(errors="replace")

    def _read_pending(self) -> str:
        """Everything already buffered on stdin, without blocking."""
        out = ""
        while select.select([self.fd], [], [], 0.02)[0]:  # 20ms: enough for one seq
            out += self._read(4096)
        return out

    async def _read_key(self) -> str:
        loop = asyncio.get_event_loop()
        if self._pending:
            ch, self._pending = self._pending[0], self._pending[1:]
        else:
            ch = await loop.run_in_executor(None, self._read, 1)
        if ch != ESC:
            return ch
        # ESC alone vs. the start of a sequence (arrows, alt-keys, paste): peek at
        # whatever arrived with it. Empty -> bare escape key.
        rest = self._pending + await loop.run_in_executor(None, self._read_pending)
        self._pending = ""
        if not rest.startswith("[200~"):  # \x1b[200~ = bracketed paste start
            return ESC + rest
        pasted = rest.removeprefix("[200~")
        while ESC + "[201~" not in pasted:  # \x1b[201~ = bracketed paste end
            pasted += await loop.run_in_executor(None, self._read, 4096)
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
        # \x1b[?25l = hide cursor; \x1b[?2004h = enable bracketed paste. The first
        # _render makes its own room, so there is nothing to reserve here.
        self._write("\x1b[?25l\x1b[?2004h")
        # A resize invalidates cols, height, the box's row count and DECSTBM all at
        # once; only a repaint re-derives them from one consistent reading.
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGWINCH, self._render, True)
        try:
            yield
        finally:
            loop.remove_signal_handler(signal.SIGWINCH)
            height = os.get_terminal_size().lines
            top = height - self._rows + 1
            # \x1b[?2004l = paste off; \x1b7 save; \x1b[r = reset scroll region;
            # goto box top, \x1b[J = clear to end of screen; \x1b8 restore;
            # \x1b[?25h = show cursor.
            self._write(f"\x1b[?2004l\x1b7\x1b[r\x1b[{top};1H\x1b[J\x1b8\x1b[?25h")
            termios.tcsetattr(self.fd, termios.TCSADRAIN, old)

    async def prompt_async(self, label: str = "❯ ") -> str:
        self.buf, self.cursor, self.pastes, self.label = "", 0, [], label
        with self._raw():
            self._render()
            while (key := await self._read_key()) != "\r":
                self._handle(key)
                self._render()
        self._write(f"{label}{self._display(self.buf)}\n")
        return self._expand()
