import asyncio
import os
import re
import threading

import pytest

from nkd_agents.tty import DIM, ESC, PASTE, RESET, REV, Prompt

NORM = "\x1b[27m"
GREEN = "\x1b[32m"
CUR = f"{REV} {NORM}"  # the fake cursor on an empty cell
SGR = re.compile(r"\x1b\[[0-9;]*m")
# a "\x1b[<row>;1H\x1b[2K" jump followed by text and colors, up to the next jump
ROW = re.compile(r"\x1b\[(\d+);1H\x1b\[2K((?:[^\x1b]|\x1b\[[0-9;]*m)*)")


def rule(cols: int) -> str:
    return f"{DIM}{'─' * cols}{RESET}"


def dim(s: str) -> str:
    return f"{DIM}{s}{RESET}"


def room(rows: int) -> str:
    """A normal render makes room relative to the cursor: full-screen region (which
    homes the cursor on a real terminal, hence the save/restore around it), `rows`
    indexes, cursor back. The indexes scroll only if the room isn't there yet."""
    return "\x1b7\x1b[r\x1b8" + "\x1bD" * rows + f"\x1b[{rows}A"


def anchor(top: int) -> str:
    """A resize cannot go relative - the cursor moved - so it erases the re-wrapped
    box and puts the cursor on the row above the box absolutely."""
    return f"\x1b[J\x1b[r\x1b[{top - 1};1H"


def painted(out: str) -> dict[int, str]:
    """{row number: what was painted there}. Rows written more than once keep the
    last write, which is what the screen would show."""
    return {int(row): text for row, text in ROW.findall(out)}


def cells(text: str) -> int:
    """Width of a painted row in terminal cells: colors take up none."""
    return len(SGR.sub("", text))


@pytest.fixture
def p() -> Prompt:
    prompt = Prompt()
    prompt.label = "> "
    return prompt


def type_(p: Prompt, s: str) -> None:
    for ch in s:
        p._handle(ch)


class TestEditing:
    @pytest.mark.parametrize("key", ["\x7f", "\x08", ESC + "\x7f", "\x17"])
    def test_deletion_keys_do_nothing(self, p: Prompt, key: str) -> None:
        type_(p, "ab")
        p._handle(key)
        assert p.buf == "ab"

    def test_key_bindings_and_defaults(self, p: Prompt) -> None:
        hits: list[str] = []
        p.key_bindings = {
            "\t": lambda _: hits.append("tab"),
            ESC: lambda _: hits.append("esc"),
            "\x03": lambda _: hits.append("never"),  # built-ins win
        }
        p._handle("\t")
        p._handle(ESC)
        assert hits == ["tab", "esc"]
        with pytest.raises(KeyboardInterrupt):
            p._handle("\x03")
        with pytest.raises(EOFError):
            p._handle("\x04")
        type_(p, "x")
        p._handle("\x04")  # ctrl-d with text is a no-op
        assert p.buf == "x"


class TestPaste:
    def test_is_appended_raw(self, p: Prompt) -> None:
        type_(p, "see ")
        p._handle(PASTE + "l1\nl2")
        type_(p, " ok")
        assert p.buf == "see l1\nl2 ok"

    @pytest.mark.parametrize(
        "line_ending", ["\n", "\r", "\r\n"], ids=["lf", "cr", "crlf"]
    )
    def test_any_line_ending_becomes_newline(self, p: Prompt, line_ending: str) -> None:
        p._handle(PASTE + line_ending.join(["l1", "l2", "l3"]))
        assert p.buf == "l1\nl2\nl3"


class TestInputRow:
    def test_fits_and_marks_cursor(self, p: Prompt) -> None:
        type_(p, "abc")
        assert p._input_row(cols=10) == f"> abc{CUR}"

    def test_scrolls_to_keep_cursor_at_the_end_in_view(self, p: Prompt) -> None:
        type_(p, "abcdefghij")  # "> abcdefghij" = 12 chars
        assert p._input_row(cols=5) == f"ghij{CUR}"

    def test_is_always_at_most_cols_wide(self, p: Prompt) -> None:
        type_(p, "x" * 500)
        assert cells(p._input_row(cols=7)) == 7

    def test_paste_newline_shows_as_space(self, p: Prompt) -> None:
        p._handle(PASTE + "x\ny")
        type_(p, "z")
        assert p._input_row(cols=40) == f"> x yz{CUR}"


class TestRender:
    """Geometry at 10x20 with a 1-row input: rows 17=rule, 18=input, 19=rule, 20=tb,
    so the box is 4 rows and the scroll region is 1..16. Each extra input row pushes
    the top of the box (and the region's bottom) up by one."""

    COLS, LINES = 10, 20

    @pytest.fixture
    def screen(self, p: Prompt, monkeypatch, capsys):
        monkeypatch.setattr(
            os,
            "get_terminal_size",
            lambda *_: os.terminal_size((self.COLS, self.LINES)),
        )
        p.toolbar = lambda: "tb"
        return p, capsys

    def test_initial_box(self, screen) -> None:
        p, capsys = screen
        p._render()
        out = capsys.readouterr().out
        assert "\x1b[1;16r" in out  # scroll region ends above the 4-row box
        assert out.startswith(room(4))  # first draw scrolls output up to make room
        assert painted(out) == {
            17: rule(10),
            18: f"> {CUR}",
            19: rule(10),
            20: dim("tb"),
        }
        assert out.endswith("\x1b8")  # cursor left in the output area

    def test_overflow_scrolls_horizontally_and_box_keeps_its_height(
        self, screen
    ) -> None:
        p, capsys = screen
        p._render()
        capsys.readouterr()

        type_(p, "abcdefghijkl")  # "> " + 12 chars > 10 cols
        p._render()
        out = capsys.readouterr().out
        assert "\x1b[1;16r" in out and room(4) in out
        assert painted(out) == {
            17: rule(10),
            18: f"defghijkl{CUR}",
            19: rule(10),
            20: dim("tb"),
        }

    def test_resize_erases_the_reflowed_box(self, screen) -> None:
        p, capsys = screen
        p._render()
        capsys.readouterr()

        p._render(resized=True)  # SIGWINCH: same size, but the box was reflowed
        out = capsys.readouterr().out
        # erase whatever the box reflowed into, then re-make room and repaint
        assert out.startswith(anchor(top=17))
        assert "\x1b[1;16r" in out
        assert painted(out) == {
            17: rule(10),
            18: f"> {CUR}",
            19: rule(10),
            20: dim("tb"),
        }

    def test_resize_repaints_at_the_new_width(self, screen) -> None:
        p, capsys = screen
        p.buf = "abcdefgh"
        p._render()
        capsys.readouterr()

        self.COLS = 5
        p._render(resized=True)
        out = capsys.readouterr().out
        assert anchor(top=17) in out
        assert painted(out) == {
            17: rule(5),  # the rule narrows with the terminal
            18: f"efgh{CUR}",
            19: rule(5),
            20: dim("tb"),
        }

    def test_no_row_ever_exceeds_cols(self, screen) -> None:
        """A row wider than the terminal wraps; on the bottom row that scrolls the
        whole screen and the box walks upward. Clipping is what makes the painted
        height equal the computed height, which every other calculation assumes."""
        p, capsys = screen
        p.toolbar = lambda: "model (ctrl-l)  mode (shift-tab)  think:off (tab)"
        type_(p, "abcdefghijklmnop")
        p._render()
        rows = painted(capsys.readouterr().out)
        assert rows and all(cells(text) <= self.COLS for text in rows.values())
        assert rows[20] == dim("model (ctr")  # the toolbar is cut, not wrapped

    def test_toolbar_newline_cannot_scroll_the_screen(self, screen) -> None:
        p, capsys = screen
        p.toolbar = lambda: "a\nb"
        p._render()
        assert painted(capsys.readouterr().out)[20] == dim("a b")

    def test_style_and_border_are_honored(self, screen) -> None:
        p, capsys = screen
        p.style = GREEN
        p.toolbar = lambda: "busy model (ctrl-l)  think:off (tab)"
        p._render()
        rows = painted(capsys.readouterr().out)
        assert rows[17] == GREEN + "─" * 10 + RESET
        assert rows[20] == f"{GREEN}busy model{RESET}"

    def test_never_writes_a_bare_newline(self, screen) -> None:
        """cbreak leaves OPOST|ONLCR on, so a "\\n" reaches the terminal as CR+LF and
        moves the cursor to column 1 - truncating any output line written without a
        trailing newline. _room indexes with \\x1bD instead. This is the one guard on
        that: pyte does not model ONLCR, so no screen test can catch it."""
        p, capsys = screen
        p._render()  # steady state, growth and resize all make room
        type_(p, "abcdefghijkl")
        p._render()
        p._render(resized=True)
        assert "\n" not in capsys.readouterr().out


class TestGeometryIsAlwaysOnScreen:
    """Every row and region index we emit must be a real screen position. A tall
    buffer or a tiny terminal used to produce \\x1b[1;-5r and \\x1b[-4;1H, which a
    terminal either ignores or obeys catastrophically."""

    # (row, col) pairs from any escape that takes a screen position or a count
    POSITIONS = re.compile(r"\x1b\[(-?\d+)(?:;(-?\d+))?[rHSA]")
    SIZES = [(0, 1), (1, 1), (1, 24), (2, 3), (5, 4), (20, 8), (80, 24)]
    BUFFERS = {
        "empty": "",
        "short": "ab",
        "one long line": "x" * 500,
        "many lines": "\n".join(f"line {i}" for i in range(40)),
    }
    buffers = pytest.mark.parametrize("buf", BUFFERS.values(), ids=BUFFERS)

    @pytest.mark.parametrize("cols,lines", SIZES)
    @buffers
    def test_no_escape_addresses_off_screen(
        self, p: Prompt, monkeypatch, capsys, cols: int, lines: int, buf: str
    ) -> None:
        p.toolbar = lambda: "toolbar text that is plausibly long"
        p.buf = buf
        monkeypatch.setattr(
            os, "get_terminal_size", lambda *_: os.terminal_size((cols, lines))
        )
        p._render()  # first draw, then a redraw and a resize: all three must be safe
        p._render()
        p._render(resized=True)
        out = capsys.readouterr().out
        found = [int(g) for m in self.POSITIONS.finditer(out) for g in m.groups() if g]
        assert found and all(n >= 1 for n in found), out[:200]

    @pytest.mark.parametrize("cols,lines", SIZES)
    @buffers
    def test_box_never_claims_the_whole_screen(
        self, p: Prompt, monkeypatch, capsys, cols: int, lines: int, buf: str
    ) -> None:
        """Row 1 always stays outside the box, or output has nowhere to scroll.
        On a screen too short to hold any box at all, nothing is painted, which
        satisfies this trivially - the point is that row 1 is never claimed."""
        p.buf = buf
        monkeypatch.setattr(
            os, "get_terminal_size", lambda *_: os.terminal_size((cols, lines))
        )
        p._render()
        assert all(row >= 2 for row in painted(capsys.readouterr().out))


class TestReadKey:
    @pytest.fixture
    def piped(self, p: Prompt):
        r, w = os.pipe()
        p.fd = r
        yield p, w
        os.close(r)
        os.close(w)

    def test_plain_and_escape(self, piped) -> None:
        p, w = piped
        os.write(w, b"a" + ESC.encode() + b"[A")
        assert asyncio.run(p._read_key()) == "a"
        assert asyncio.run(p._read_key()) == ESC + "[A"

    def test_bare_escape(self, piped) -> None:
        p, w = piped
        os.write(w, ESC.encode())
        assert asyncio.run(p._read_key()) == ESC

    def test_alt_sequence_is_one_key_that_misses_the_bare_escape_binding(
        self, piped
    ) -> None:
        p, w = piped
        hits: list[str] = []
        p.key_bindings = {ESC: lambda _: hits.append("esc")}
        p.buf = "ab"
        os.write(w, (ESC + "\x7f").encode())
        key = asyncio.run(p._read_key())
        assert key == ESC + "\x7f"
        p._handle(key)
        assert hits == []
        assert p.buf == "ab"

    @pytest.mark.parametrize("seq", ["[A", "[Z", "OP", "x"])
    def test_escape_sequences_are_dropped_not_interrupts(self, piped, seq: str) -> None:
        p, w = piped
        hits: list[str] = []
        p.key_bindings = {ESC: lambda _: hits.append("esc")}
        p.buf = "ab"
        os.write(w, (ESC + seq).encode())
        p._handle(asyncio.run(p._read_key()))
        assert hits == []
        assert p.buf == "ab"

    def test_escape_byte_inside_paste_is_kept(self, piped) -> None:
        p, w = piped
        os.write(w, f"{ESC}[200~a{ESC}[Ab{ESC}[201~".encode())
        p._handle(asyncio.run(p._read_key()))
        assert p.buf == f"a{ESC}[Ab"

    def test_printable_chunk_is_read_one_char_per_key(self, piped) -> None:
        p, w = piped
        os.write(w, b"abc")
        keys = [asyncio.run(p._read_key()) for _ in range(3)]
        assert keys == ["a", "b", "c"]

    def test_bracketed_paste_keeps_trailing_input(self, piped) -> None:
        p, w = piped
        os.write(w, f"{ESC}[200~x\ny{ESC}[201~z".encode())
        assert asyncio.run(p._read_key()) == PASTE + "x\ny"
        assert asyncio.run(p._read_key()) == "z"

    def test_multibyte_char_is_one_key(self, piped) -> None:
        """Reading a byte at a time split UTF-8 sequences into U+FFFD pairs."""
        p, w = piped
        os.write(w, "é".encode())
        assert asyncio.run(p._read_key()) == "é"

    def test_cancelled_read_leaves_no_reader_and_no_thread(self, piped) -> None:
        """ctrl-c cancels the read. With run_in_executor the worker stayed blocked in
        os.read and the interpreter hung joining it at exit; add_reader is removed."""
        p, w = piped
        before = threading.enumerate()

        async def drive() -> bool:
            task = asyncio.ensure_future(p._read_key())
            await asyncio.sleep(0)  # let it register
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            os.write(w, b"x")  # would wake a blocked worker; must reach nobody
            return asyncio.get_running_loop().remove_reader(p.fd)

        assert asyncio.run(drive()) is False  # nothing was still registered
        assert threading.enumerate() == before
