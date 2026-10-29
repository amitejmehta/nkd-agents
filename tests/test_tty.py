import asyncio
import contextlib
import logging
import os
import sys
import termios
from collections.abc import AsyncGenerator, Callable
from types import SimpleNamespace

import pytest

from nkd_agents import tty
from nkd_agents.tty import TUI, TUIHandler, cell_width

ESC = "\x1b"


@pytest.fixture
def cols(monkeypatch: pytest.MonkeyPatch) -> Callable[[int], None]:
    def set_cols(n: int) -> None:
        monkeypatch.setattr(
            tty.shutil, "get_terminal_size", lambda *a, **k: os.terminal_size((n, 24))
        )

    set_cols(20)
    return set_cols


@pytest.fixture
def drive(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    def run(ui: TUI, chunks: list[str], bindings: dict | None = None) -> None:
        async def fake_keys() -> AsyncGenerator[str]:
            for chunk in chunks:
                yield chunk

        monkeypatch.setattr(tty, "keys", fake_keys)
        asyncio.run(ui.input_loop(bindings or {}))

    return run


@pytest.mark.parametrize(
    "char,width", [("a", 1), ("日", 2), ("\u0301", 0), ("😀", 2), ("ｗ", 2)]
)
def test_cell_width(char: str, width: int) -> None:
    assert cell_width(char) == width


class TestDraw:
    def test_label_then_buffer(self, cols, capsys) -> None:
        ui = TUI(lambda: "> ")
        ui.buf = "abc"
        ui.draw()
        assert capsys.readouterr().out == "\r\x1b[K> abc"

    def test_keeps_tail_within_cols_minus_one(self, cols, capsys) -> None:
        cols(6)
        ui = TUI(lambda: "> ")
        ui.buf = "abcdefghij"
        ui.draw()
        assert capsys.readouterr().out.endswith("hij")

    def test_wide_char_never_straddles_edge(self, cols, capsys) -> None:
        cols(6)
        ui = TUI(lambda: "> ")
        ui.buf = "a日本語"
        ui.draw()
        assert capsys.readouterr().out.endswith("語")

    def test_newlines_become_spaces(self, cols, capsys) -> None:
        ui = TUI(lambda: "a\nb ")
        ui.buf = "x\ny"
        ui.draw()
        assert capsys.readouterr().out == "\r\x1b[Ka b x y"

    def test_empty_buffer_shows_label_only(self, cols, capsys) -> None:
        ui = TUI(lambda: "> ")
        ui.draw()
        assert capsys.readouterr().out == "\r\x1b[K> "


class TestLog:
    def test_clears_line_converts_newlines_and_redraws(self, cols, capsys) -> None:
        ui = TUI(lambda: "> ")
        ui.buf = "hi"
        ui.log("a\nb")
        assert capsys.readouterr().out == ("\r\x1b[Ka\r\nb\r\n\r\x1b[K> hi")


class TestTUIHandler:
    def test_emit_logs_through_tui(self, cols, capsys) -> None:
        ui = TUI(lambda: "> ")
        ui.buf = "hi"
        rec = logging.LogRecord("n", logging.INFO, "", 0, "msg", None, None)
        TUIHandler(ui).emit(rec)
        assert capsys.readouterr().out == "\r\x1b[Kmsg\r\n\r\x1b[K> hi"


class TestPaste:
    @pytest.mark.parametrize("ending", ["\n", "\r", "\r\n"], ids=["lf", "cr", "crlf"])
    def test_line_endings_become_newline(self, ending: str) -> None:
        ui = TUI()
        ui.paste(ending.join(["l1", "l2", "l3"]))
        assert ui.buf == "l1\nl2\nl3"

    def test_control_chars_dropped_newlines_kept(self) -> None:
        ui = TUI()
        ui.paste(f"a{ESC}[Ab\tc\nd")
        assert ui.buf == "a[Abc\nd"

    def test_appends_to_existing_buffer(self) -> None:
        ui = TUI()
        ui.buf = "see "
        ui.paste("x")
        assert ui.buf == "see x"


class TestPrompt:
    def test_typing_appends_printable(self, cols, drive) -> None:
        ui = TUI()
        drive(ui, ["a", "bc", "é", "😀"])
        assert ui.buf == "abcé😀"

    def test_control_chars_not_inserted(self, cols, drive) -> None:
        ui = TUI()
        drive(ui, ["a\x01\x7fb"])
        assert ui.buf == "ab"

    def test_whole_key_binding(self, cols, drive) -> None:
        hits: list[str] = []
        drive(
            TUI(),
            ["\t", ESC, ESC + "[Z"],
            {
                "\t": lambda: hits.append("tab"),
                ESC: lambda: hits.append("esc"),
                ESC + "[Z": lambda: hits.append("shift-tab"),
            },
        )
        assert hits == ["tab", "esc", "shift-tab"]

    def test_binding_fires_per_char_in_chunk(self, cols, drive) -> None:
        ui = TUI()
        drive(ui, ["ab\rcd"], {"\r": lambda: setattr(ui, "buf", "")})
        assert ui.buf == "cd"

    def test_bound_key_is_not_inserted(self, cols, drive) -> None:
        ui = TUI()
        drive(ui, ["\t"], {"\t": lambda: None})
        assert ui.buf == ""

    @pytest.mark.parametrize("seq", ["[A", "[Z", "OP", "x", "\x7f"])
    def test_unbound_escape_sequences_dropped(self, cols, drive, seq: str) -> None:
        hits: list[str] = []
        ui = TUI()
        ui.buf = "ab"
        drive(ui, [ESC + seq], {ESC: lambda: hits.append("esc")})
        assert hits == []
        assert ui.buf == "ab"

    def test_binding_exception_propagates(self, cols, drive) -> None:
        def quit() -> None:
            raise EOFError

        with pytest.raises(EOFError):
            drive(TUI(), ["\x03"], {"\x03": quit})

    def test_paste_in_one_chunk_keeps_trailing_input(self, cols, drive) -> None:
        ui = TUI()
        drive(ui, ["\x1b[200~l1\nl2\x1b[201~y"])
        assert ui.buf == "l1\nl2y"

    def test_paste_split_across_chunks(self, cols, drive) -> None:
        ui = TUI()
        drive(ui, ["\x1b[200~a\r", "b\t", "c\x1b[201~z"])
        assert ui.buf == "a\nbcz"

    def test_paste_content_does_not_trigger_bindings(self, cols, drive) -> None:
        hits: list[str] = []
        ui = TUI()
        drive(
            ui,
            ["\x1b[200~a\rb\x1b[201~"],
            {"\r": lambda: hits.append("cr")},
        )
        assert hits == []
        assert ui.buf == "a\nb"

    def test_redraws_after_every_key(self, cols, drive, capsys) -> None:
        drive(TUI(lambda: "> "), ["a", "b"])
        assert capsys.readouterr().out.count("\r\x1b[K") == 3


class TestKeys:
    @pytest.fixture
    def pipe(self, monkeypatch: pytest.MonkeyPatch):
        r, w = os.pipe()
        monkeypatch.setattr(sys, "stdin", SimpleNamespace(fileno=lambda: r))
        monkeypatch.setattr(tty, "raw", lambda fd: contextlib.nullcontext())
        yield r, w
        os.close(r)
        os.close(w)

    def test_yields_read_chunks(self, pipe) -> None:
        _, w = pipe
        os.write(w, b"abc")

        async def go() -> str:
            async with contextlib.aclosing(tty.keys()) as ks:
                return await asyncio.wait_for(anext(ks), 1)

        assert asyncio.run(go()) == "abc"

    @pytest.mark.parametrize("char", ["é", "€", "😀"])
    def test_utf8_split_across_reads(self, pipe, char: str) -> None:
        _, w = pipe

        async def go() -> str:
            async with contextlib.aclosing(tty.keys()) as ks:
                for b in char.encode():
                    os.write(w, bytes([b]))
                    await asyncio.sleep(0.01)
                os.write(w, b"!")
                out = ""
                while not out.endswith("!"):
                    out += await asyncio.wait_for(anext(ks), 1)
                return out

        assert asyncio.run(go()) == char + "!"

    def test_reader_removed_on_close(self, pipe) -> None:
        r, _ = pipe

        async def go() -> bool:
            ks = tty.keys()
            task = asyncio.ensure_future(anext(ks))
            await asyncio.sleep(0.01)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await ks.aclose()
            return asyncio.get_running_loop().remove_reader(r)

        assert asyncio.run(go()) is False


class TestRaw:
    def test_sets_and_restores_terminal_on_error(self, monkeypatch, capsys) -> None:
        calls: list[tuple] = []
        state = [0, 0, 0, 0xFFFF, 0, 0, [0] * 32]
        monkeypatch.setattr(
            termios, "tcgetattr", lambda fd: [*state[:6], list(state[6])]
        )
        monkeypatch.setattr(
            termios, "tcsetattr", lambda fd, when, attrs: calls.append((when, attrs))
        )
        with pytest.raises(RuntimeError), tty.raw(0):
            assert capsys.readouterr().out == "\x1b[?2004h"
            raise RuntimeError
        assert capsys.readouterr().out == "\x1b[?2004l"
        (when1, new), (when2, old) = calls
        assert (when1, when2) == (termios.TCSANOW, termios.TCSADRAIN)
        assert not new[3] & (termios.ECHO | termios.ICANON | termios.ISIG)
        assert new[6][termios.VMIN] == 1
        assert old[3] == 0xFFFF
