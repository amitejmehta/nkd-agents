"""What the user actually sees, via a VT emulator.

tests/test_tty.py asserts the escape stream `_render` *emits*. That cannot catch a
bug where correct-looking escapes produce a wrong screen - notably the claim the
whole design rests on: output printed while the prompt is up scrolls above the box
and never touches it. Here the same escapes drive pyte and we read the screen.

One limit, so nobody mistakes green here for full coverage:
  - pyte's resize() clips and pads, it does not re-wrap. The reflow-on-resize bug
    these tests grew out of is NOT reproducible; only a real terminal shows it.
"""

import asyncio
import os
import signal
import termios
import tty
from unittest.mock import patch

import pytest

from nkd_agents.tty import CHROME, Prompt

pyte = pytest.importorskip("pyte")


class Term:
    """A Prompt whose writes land in a real emulator instead of stdout."""

    def __init__(self, cols: int = 24, lines: int = 8, toolbar: str = "tb") -> None:
        self.screen = pyte.Screen(cols, lines)
        self.stream = pyte.Stream(self.screen)  # type: ignore[attr-defined]
        self.size = os.terminal_size((cols, lines))
        self.prompt = Prompt(toolbar=lambda: toolbar)
        self.prompt.label = "> "
        self.prompt._write = self.feed  # type: ignore[method-assign]

    def feed(self, text: str) -> None:
        """Anything a program writes to the terminal: box escapes or plain output."""
        self.stream.feed(text)

    def render(self, resized: bool = False) -> None:
        with patch.object(os, "get_terminal_size", return_value=self.size):
            self.prompt._render(resized)

    def type(self, text: str) -> None:
        for ch in text:
            self.prompt._handle(ch)

    @property
    def rows(self) -> list[str]:
        return [row.rstrip() for row in self.screen.display]

    @property
    def box(self) -> list[str]:
        return self.rows[-self.prompt._rows :]

    @property
    def above(self) -> list[str]:
        return self.rows[: -self.prompt._rows]

    @property
    def last_output(self) -> str:
        """Last non-blank row above the box - the newest thing the program wrote.
        The literal last row above is normally the blank one holding the cursor."""
        return next((row for row in reversed(self.above) if row), "")


@pytest.fixture
def term() -> Term:
    """A prompt started under four lines of prior output, as in a real session."""
    t = Term()
    t.feed("".join(f"output {i}\r\n" for i in range(4)))
    t.render()
    return t


class TestOutputNeverTouchesTheBox:
    """Design choice #1: writers do not coordinate with the prompt at all."""

    def test_a_line_of_output_scrolls_above_the_box(self, term: Term) -> None:
        before = term.box
        term.feed("hello\r\n")
        assert term.box == before  # the box is untouched, byte for byte
        assert term.last_output == "hello"

    def test_output_longer_than_the_screen_never_reaches_the_box(
        self, term: Term
    ) -> None:
        before = term.box
        term.feed("".join(f"line {i}\r\n" for i in range(200)))
        assert term.box == before
        assert term.last_output == "line 199"

    def test_output_without_a_trailing_newline_stays_above(self, term: Term) -> None:
        before = term.box
        term.feed("no newline here")
        assert term.box == before
        assert term.last_output == "no newline here"

    def test_a_render_between_writes_does_not_disturb_output(self, term: Term) -> None:
        term.feed("first\r\n")
        above = term.above
        term.type("abc")
        term.render()
        assert term.above == above  # typing repaints the box, not the output


class TestCursorStaysInTheOutputArea:
    """_reset's \\x1b[J erases from the cursor down, so it is only safe while the
    cursor sits above the box. Nothing else checks that."""

    def test_after_render_the_cursor_is_above_the_box(self, term: Term) -> None:
        assert term.screen.cursor.y < term.screen.lines - term.prompt._rows

    def test_still_above_after_the_box_grows(self, term: Term) -> None:
        term.type("a" * 50)  # wraps across several rows
        term.render()
        assert term.screen.cursor.y < term.screen.lines - term.prompt._rows

    def test_still_above_after_output_and_renders(self, term: Term) -> None:
        for i in range(30):
            term.feed(f"out {i}\r\n")
            term.type("x")
            term.render()
        assert term.screen.cursor.y < term.screen.lines - term.prompt._rows


class TestResizeToANewHeight:
    """A height change moves the cursor, so the box's row count from the last render
    says nothing about where it is. Making room relative to it scrolled output away,
    a line per row of box - and only width was ever tested.

    These build the post-resize state by hand rather than calling pyte's resize(),
    which reorders rows instead of clipping them.
    """

    def arrive(
        self, lines: int, cursor_row: int, stale_rows: int = 4
    ) -> tuple[Term, list[str]]:
        """A prompt that last rendered a `stale_rows` box at some other height, now
        on a `lines`-tall screen with the cursor parked wherever the terminal left
        it. Returns the terminal and the rows as they were before the repaint."""
        t = Term(cols=20, lines=lines)
        t.feed("".join(f"out {i}\r\n" for i in range(5)))
        t.prompt._rows = stale_rows
        t.screen.cursor_position(cursor_row, 1)
        before = t.rows
        t.render(resized=True)
        return t, before

    @pytest.mark.parametrize("cursor_row", [4, 7, 8], ids=["mid", "near", "bottom"])
    def test_rows_above_the_cursor_are_never_scrolled(self, cursor_row: int) -> None:
        t, before = self.arrive(lines=8, cursor_row=cursor_row)
        keep = min(cursor_row, t.screen.lines - t.prompt._rows) - 1
        assert keep and t.rows[:keep] == before[:keep], t.rows

    def test_cursor_is_anchored_one_row_above_the_box(self) -> None:
        t, _ = self.arrive(lines=8, cursor_row=8)  # the case that ate output
        assert t.screen.cursor.y == t.screen.lines - t.prompt._rows - 1

    @pytest.mark.parametrize("lines", [8, 12, 20])
    def test_box_is_pinned_to_the_bottom_of_the_new_height(self, lines: int) -> None:
        t, _ = self.arrive(lines=lines, cursor_row=lines)
        assert t.rows[-1] == "tb"
        assert t.rows[-2].startswith("─")
        assert len(t.box) == CHROME + 1


class TestBoxIntegrity:
    def test_overflowing_toolbar_would_destroy_output(self) -> None:
        """The consequence behind test_no_row_ever_exceeds_cols: without the clip,
        the toolbar wraps and its tail lands on a line of real output."""
        t = Term(cols=20, toolbar=" claude-sonnet-5 (c-l)  think:off (tab)")
        t.feed("".join(f"output {i}\r\n" for i in range(4)))
        t.render()
        t.type("h")
        t.render()
        assert t.last_output == "output 3"  # not the toolbar's wrapped remainder
        assert len(t.box) == CHROME + 1

    def test_repeated_renders_do_not_drift(self, term: Term) -> None:
        term.type("hello")
        term.render()
        stable = term.rows
        for _ in range(50):
            term.render()
        assert term.rows == stable

    def test_shrinking_the_box_leaves_no_ghost_row(self, term: Term) -> None:
        term.type("a" * 23)  # wraps to a second row
        term.render()
        tall = len(term.box)
        term.prompt._handle("\x7f")  # still wrapped: one char short of the boundary
        term.prompt._handle("\x7f")  # drops below it: back to one row
        term.render()
        assert len(term.box) == tall - 1
        assert term.last_output == "output 3"  # the freed row is blank, not stale box

    def test_growing_the_box_scrolls_output_up_by_one(self, term: Term) -> None:
        assert term.last_output == "output 3"
        term.type("a" * 22)  # exactly fills the row: wraps to a second, empty row
        term.render()
        assert term.last_output == "output 3"  # still there, just one row higher
        assert len(term.box) == CHROME + 2


class TestWholeSession:
    """_raw's teardown is the only thing that ever removes the box, and nothing
    else exercises _raw or prompt_async. Drive a real session end to end."""

    def run(self, t: Term, keys: bytes, monkeypatch) -> str:
        r, w = os.pipe()
        t.prompt.fd = r
        monkeypatch.setattr(tty, "setcbreak", lambda *_: None)  # no real terminal here
        monkeypatch.setattr(termios, "tcgetattr", lambda *_: [0] * 7)
        monkeypatch.setattr(termios, "tcsetattr", lambda *_: None)
        os.write(w, keys)
        try:
            with patch.object(os, "get_terminal_size", return_value=t.size):
                return asyncio.run(t.prompt.prompt_async("> "))
        finally:
            os.close(r)
            os.close(w)

    def test_submitting_leaves_a_clean_screen(self, monkeypatch) -> None:
        t = Term(lines=12)
        t.feed("".join(f"output {i}\r\n" for i in range(4)))
        assert self.run(t, b"hi\r", monkeypatch) == "hi"
        assert not [row for row in t.rows if "─" in row or row == "tb"]  # box erased
        assert "output 3" in t.rows  # prior output survived the session
        assert "> hi" in t.rows  # the submitted line is left in the scrollback

    def test_second_prompt_does_not_reclaim_the_last_box(self, monkeypatch) -> None:
        """_rows outlives teardown. Unreset, the next prompt's first render treats the
        old (taller) box's rows as freed by a shrink and blanks them. The row it hits
        is the cursor's, which is blank after a finished reply - but holds the tail
        of an interrupted one, printed with no trailing newline."""
        t = Term(lines=12)
        t.feed("".join(f"output {i}\r\n" for i in range(12)))  # full: cursor at bottom
        assert self.run(t, b"a" * 22 + b"\r", monkeypatch) == "a" * 22  # 2-row input
        t.feed("reply cut off by ctrl-c")
        assert self.run(t, b"\r", monkeypatch) == ""
        # the next echo lands on the same row (no newline to end it) - that is the
        # writer's business; the point is that the reply itself is still there
        assert any(row.startswith("reply cut off by ctrl-c") for row in t.rows)

    def test_echo_starts_on_its_own_line(self, monkeypatch) -> None:
        """A reply streamed with end="" leaves the cursor mid-line. The echo cannot
        know that, so it always begins with a newline: `the silence h> continue`
        was the alternative."""
        t = Term(lines=12)
        t.feed("the silence h")  # no trailing newline
        self.run(t, b"continue\r", monkeypatch)
        assert "the silence h" in t.rows  # intact: nothing was written after it
        # pyte has no ONLCR, so its "\n" keeps the column; a real tty returns to 1
        assert any(row.lstrip() == "> continue" for row in t.rows)

    def test_echo_is_styled(self, monkeypatch) -> None:
        """The submitted line takes `style`, so it reads apart from the reply."""
        t = Term(lines=12)
        self.run(t, b"hi\r", monkeypatch)
        y = t.rows.index("> hi")
        assert t.screen.buffer[y][0].fg != "default"

    def test_a_paste_survives_the_round_trip(self, monkeypatch) -> None:
        t = Term(lines=12)
        paste = b"\x1b[200~one\ntwo\x1b[201~"
        assert self.run(t, paste + b"\r", monkeypatch) == "one\ntwo"
        assert not [row for row in t.rows if "─" in row]

    def test_sigwinch_repaints_the_box(self, monkeypatch) -> None:
        """The bug this whole module grew out of: without a SIGWINCH handler the box
        is only repainted on a keystroke, so a resize leaves it stale. Deliver a real
        signal mid-session and check a resize-repaint actually ran."""
        t = Term(lines=12)
        resized: list[bool] = []
        real = t.prompt._render
        t.prompt._render = lambda r=False: (resized.append(r), real(r))[1]  # type: ignore[method-assign]

        r, w = os.pipe()
        t.prompt.fd = r
        monkeypatch.setattr(tty, "setcbreak", lambda *_: None)
        monkeypatch.setattr(termios, "tcgetattr", lambda *_: [0] * 7)
        monkeypatch.setattr(termios, "tcsetattr", lambda *_: None)

        async def drive() -> str:
            task = asyncio.ensure_future(t.prompt.prompt_async("> "))
            await asyncio.sleep(0.05)  # let it reach the read
            os.kill(os.getpid(), signal.SIGWINCH)
            await asyncio.sleep(0.05)  # let the loop run the handler
            os.write(w, b"\r")
            return await task

        try:
            with patch.object(os, "get_terminal_size", return_value=t.size):
                assert asyncio.run(drive()) == ""
        finally:
            os.close(r)
            os.close(w)
        assert any(resized), "SIGWINCH did not trigger a resize repaint"
