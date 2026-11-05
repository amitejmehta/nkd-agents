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
from nkd_agents.tty import TUI

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
def drive(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[str]]:
    def run(ui: TUI, chunks: list[str]) -> list[str]:
        got: list[str] = []

        async def fake_keys() -> AsyncGenerator[str]:
            for chunk in chunks:
                yield chunk

        monkeypatch.setattr(tty, "keys", fake_keys)
        asyncio.run(ui.input_loop(got.append))
        return got

    return run


class TestDraw:
    def test_renders_text(self, cols, capsys) -> None:
        TUI(lambda: "> hi").draw()
        assert capsys.readouterr().out == "\r\x1b[K> hi"

    def test_keeps_tail_within_cols_minus_one(self, cols, capsys) -> None:
        cols(6)
        TUI(lambda: "abcdefghij").draw()
        assert capsys.readouterr().out == "\r\x1b[Kfghij"

    def test_huge_buffer_keeps_tail(self, cols, capsys) -> None:
        cols(6)
        ui = TUI()
        ui.buf = "x" * 1_000_000 + "abcde"
        ui.draw()
        assert capsys.readouterr().out == "\r\x1b[Kabcde"

    def test_newlines_become_spaces(self, cols, capsys) -> None:
        ui = TUI()
        ui.buf = "a\nb c"
        ui.draw()
        assert capsys.readouterr().out == "\r\x1b[Ka b c"

    def test_wide_chars_count_double(self, cols, capsys) -> None:
        cols(6)
        TUI(lambda: "日本語日本").draw()
        assert capsys.readouterr().out == "\r\x1b[K日本"


class TestWrite:
    def test_clears_line_writes_and_redraws(self, cols, capsys) -> None:
        TUI(lambda: "> ").write("hello\n")
        assert capsys.readouterr().out == "\r\x1b[Khello\n\r\x1b[K> "

    def test_flush_is_noop(self) -> None:
        TUI().flush()

    def test_works_as_logging_stream(self, cols, capsys) -> None:
        log = logging.getLogger("test_tui_stream")
        log.propagate = False
        log.setLevel(logging.INFO)
        handler = logging.StreamHandler(TUI(lambda: "> "))
        handler.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(handler)
        try:
            log.info("hi")
        finally:
            log.removeHandler(handler)
        assert capsys.readouterr().out == "\r\x1b[Khi\n\r\x1b[K> "


class TestClean:
    @pytest.mark.parametrize("ending", ["\r\n", "\r", "\n"])
    def test_line_endings_become_newline(self, ending: str) -> None:
        assert tty.clean(f"a{ending}b") == "a\nb"

    def test_control_chars_dropped_newlines_kept(self) -> None:
        assert tty.clean("a\x00b\x07\nc") == "ab\nc"

    def test_tab_becomes_spaces(self) -> None:
        assert tty.clean("a\tb") == "a    b"


class TestInputLoop:
    def test_typed_chars_go_to_buf(self, cols, drive) -> None:
        ui = TUI()
        assert drive(ui, ["ab"]) == []
        assert ui.buf == "ab"

    def test_escape_sequences_are_one_key(self, cols, drive) -> None:
        assert drive(TUI(), [ESC + "[Z", ESC]) == [ESC + "[Z", ESC]

    def test_paste_is_cleaned_into_buf(self, cols, drive) -> None:
        ui = TUI()
        assert drive(ui, ["\x1b[200~a\r\nb\x1b[201~z"]) == []
        assert ui.buf == "a\nbz"

    def test_empty_paste_ignored(self, cols, drive) -> None:
        ui = TUI()
        assert drive(ui, ["\x1b[200~\x1b[201~"]) == []
        assert ui.buf == ""

    def test_on_key_exception_propagates(self, cols, monkeypatch) -> None:
        async def fake_keys() -> AsyncGenerator[str]:
            yield "\r"

        def boom(k: str) -> None:
            raise RuntimeError

        monkeypatch.setattr(tty, "keys", fake_keys)
        with pytest.raises(RuntimeError):
            asyncio.run(TUI().input_loop(boom))

    def test_redraws_initially_and_after_each_chunk(self, cols, drive, capsys) -> None:
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
        with contextlib.suppress(OSError):
            os.close(w)

    def test_yields_read_chunks(self, pipe) -> None:
        _, w = pipe

        async def go() -> list[str]:
            async with contextlib.aclosing(tty.keys()) as ks:
                os.write(w, b"abc")
                first = await asyncio.wait_for(anext(ks), 1)
                os.write(w, b"d")
                return [first, await asyncio.wait_for(anext(ks), 1)]

        assert asyncio.run(go()) == ["abc", "d"]

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

    def test_csi_split_across_reads_is_held(self, pipe) -> None:
        _, w = pipe

        async def go() -> str:
            async with contextlib.aclosing(tty.keys()) as ks:
                os.write(w, b"\x1b[1;")
                await asyncio.sleep(0.01)
                os.write(w, b"5A")
                return await asyncio.wait_for(anext(ks), 1)

        assert asyncio.run(go()) == "\x1b[1;5A"

    def test_lone_esc_flushes_after_timeout(self, pipe) -> None:
        _, w = pipe

        async def go() -> list[str]:
            async with contextlib.aclosing(tty.keys()) as ks:
                os.write(w, b"\x1b")
                first = await asyncio.wait_for(anext(ks), 1)
                os.write(w, b"a")
                return [first, await asyncio.wait_for(anext(ks), 1)]

        assert asyncio.run(go()) == ["\x1b", "a"]

    def test_ss3_split_across_reads_is_held(self, pipe) -> None:
        _, w = pipe

        async def go() -> str:
            async with contextlib.aclosing(tty.keys()) as ks:
                os.write(w, b"\x1bO")
                await asyncio.sleep(0.01)
                os.write(w, b"P")
                return await asyncio.wait_for(anext(ks), 1)

        assert asyncio.run(go()) == "\x1bOP"

    def test_unterminated_paste_flushes_as_paste(self, pipe) -> None:
        _, w = pipe

        async def go() -> str:
            async with contextlib.aclosing(tty.keys()) as ks:
                os.write(w, b"\x1b[200~hi\r")
                return await asyncio.wait_for(anext(ks), 3)

        assert asyncio.run(go()) == "\x1b[200~hi\r\x1b[201~"

    @pytest.mark.parametrize("fail", ["eof", "oserror"])
    def test_eof_or_read_error_raises(self, pipe, monkeypatch, fail: str) -> None:
        _, w = pipe
        if fail == "eof":
            os.close(w)
        else:

            def broken(fd: int, n: int) -> bytes:
                raise OSError

            monkeypatch.setattr(tty.os, "read", broken)
            os.write(w, b"x")

        async def go() -> None:
            async with contextlib.aclosing(tty.keys()) as ks:
                await asyncio.wait_for(anext(ks), 1)

        with pytest.raises(EOFError):
            asyncio.run(go())

    def test_spurious_wakeup_is_ignored(self, pipe, monkeypatch) -> None:
        _, w = pipe
        real, calls = os.read, []

        def flaky(fd: int, n: int) -> bytes:
            calls.append(1)
            if len(calls) == 1:
                raise BlockingIOError
            return real(fd, n)

        monkeypatch.setattr(tty.os, "read", flaky)
        os.write(w, b"x")

        async def go() -> str:
            async with contextlib.aclosing(tty.keys()) as ks:
                return await asyncio.wait_for(anext(ks), 1)

        assert asyncio.run(go()) == "x"
        assert len(calls) == 2

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
        monkeypatch.setattr(os, "fpathconf", lambda fd, name: 0xFF)
        with pytest.raises(RuntimeError), tty.raw(0):
            assert capsys.readouterr().out == "\x1b[?2004h"
            raise RuntimeError
        assert capsys.readouterr().out == "\x1b[?2004l"
        (when1, new), (when2, old) = calls
        assert (when1, when2) == (termios.TCSANOW, termios.TCSADRAIN)
        assert not new[3] & (termios.ECHO | termios.ICANON)
        assert new[3] & termios.ISIG
        assert new[6][termios.VSUSP] == b"\xff"
        assert new[6][termios.VMIN] == 1
        assert old[3] == 0xFFFF
