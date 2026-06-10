"""Minimal raw-terminal input module.

Layers:
  KeyEvent        — parsed keystroke
  RawTerminal     — context manager; owns raw mode; yields KeyEvents
  InputHandler    — keybindings dict + default line-accumulation logic
  readline_input  — async line reader with history, echo, bindings

Example:
    from nkd_agents.input import readline_input, InputHandler, Interrupt
    from collections import deque

    history = deque(maxlen=1000)
    handler = InputHandler(bindings={"\x1b": my_interrupt_fn})

    async def loop():
        while True:
            try:
                line = await readline_input("> ", handler=handler, history=history)
            except Interrupt:
                cancel_llm()
            except EOFError:
                break
"""

from __future__ import annotations

import asyncio
import os
import sys
import termios
import tty
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# KeyEvent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KeyEvent:
    char: str
    ctrl: bool = False
    alt: bool = False
    escape: bool = False  # bare ESC (not part of a sequence)

    def __str__(self) -> str:
        mods = "".join(m for m, v in (("ctrl+", self.ctrl), ("alt+", self.alt)) if v)
        return f"{mods}{self.char!r}"


def _parse(data: bytes) -> KeyEvent:
    """Parse raw bytes into a KeyEvent."""
    if data == b"\x1b":
        return KeyEvent(char="\x1b", escape=True)
    if data == b"\x1b[A":
        return KeyEvent(char="up")
    if data == b"\x1b[B":
        return KeyEvent(char="down")
    if data == b"\x1b[C":
        return KeyEvent(char="right")
    if data == b"\x1b[D":
        return KeyEvent(char="left")
    if data in (b"\x1b[1;3C", b"\x1bf", b"\x1b\x1b[C"):
        return KeyEvent(char="alt_right")
    if data in (b"\x1b[1;3D", b"\x1bb", b"\x1b\x1b[D"):
        return KeyEvent(char="alt_left")
    if data in (b"\x1b\x7f", b"\x1b[3;3~"):
        return KeyEvent(char="alt_backspace")
    if len(data) == 1:
        b = data[0]
        if b == 0x7F:
            return KeyEvent(char="backspace")
        if b == 0x0D or b == 0x0A:
            return KeyEvent(char="enter")
        if 0x01 <= b <= 0x1A:  # ctrl+a .. ctrl+z
            return KeyEvent(char=chr(b + 0x60), ctrl=True)
        return KeyEvent(char=data.decode("utf-8", errors="replace"))
    return KeyEvent(char=data.decode("utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# RawTerminal
# ---------------------------------------------------------------------------


class RawTerminal:
    """Context manager that owns raw mode on stdin.

    Async-iterates KeyEvents. Safe to use from one coroutine at a time.

        async with RawTerminal() as term:
            async for event in term:
                ...
    """

    def __init__(self, fd: int | None = None) -> None:
        self._fd = fd if fd is not None else sys.stdin.fileno()
        self._old: list | None = None
        self._reader: asyncio.StreamReader | None = None
        self._transport: asyncio.BaseTransport | None = None

    async def __aenter__(self) -> RawTerminal:
        self._old = termios.tcgetattr(self._fd)
        tty.setraw(self._fd)
        loop = asyncio.get_running_loop()
        self._reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self._reader)
        self._transport, _ = await loop.connect_read_pipe(
            lambda: protocol, os.fdopen(self._fd, "rb", closefd=False)
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._transport:
            self._transport.close()
        if self._old is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)

    def __aiter__(self) -> RawTerminal:
        return self

    async def __anext__(self) -> KeyEvent:
        if self._reader is None:
            raise StopAsyncIteration
        try:
            data = await self._reader.read(32)
            if not data:
                raise StopAsyncIteration
            return _parse(data)
        except asyncio.IncompleteReadError:
            raise StopAsyncIteration


# ---------------------------------------------------------------------------
# InputHandler
# ---------------------------------------------------------------------------


class Interrupt(Exception):
    """Raised by readline_input when an interrupt binding fires."""


@dataclass
class InputHandler:
    """Maps key chars to callables. Unbound keys fall through to line accumulation.

    Binding key is the raw char string, e.g.:
      "\x1b"   — ESC
      "\x03"   — ctrl+c  (but handled separately as EOFError/Interrupt)
      "up"     — up arrow
      "down"   — down arrow

    Callable signature: () -> None | raises Interrupt | raises EOFError
    """

    bindings: dict[str, Callable[[], None]] = field(default_factory=dict)

    def dispatch(self, event: KeyEvent) -> bool:
        """Call binding if registered. Returns True if handled."""
        fn = self.bindings.get(event.char if not event.escape else "\x1b")
        if fn:
            fn()
            return True
        return False


# ---------------------------------------------------------------------------
# readline_input
# ---------------------------------------------------------------------------

_CLEAR = "\r\033[K"  # CR + erase to end of line


async def readline_input(
    prompt: str = "> ",
    *,
    handler: InputHandler | None = None,
    history: deque[str] | None = None,
) -> str:
    """Async line reader with raw terminal, echo, backspace, history, bindings.

    Returns the completed line.
    Raises Interrupt if an interrupt binding fires.
    Raises EOFError on ctrl+d.
    """
    handler = handler or InputHandler()
    buf: list[str] = []
    cursor_pos = 0  # index into buf
    hist_idx = -1  # -1 = current input
    saved: str = ""  # saved buf when navigating history

    def _render(line: str, pos: int) -> None:
        # render line, then move cursor to pos
        sys.stdout.write(f"{_CLEAR}{prompt}{line}")
        # reposition: move left by (len - pos) chars
        diff = len(line) - pos
        if diff:
            sys.stdout.write(f"\x1b[{diff}D")
        sys.stdout.flush()

    _render("", 0)

    async with RawTerminal() as term:
        async for event in term:
            # ctrl+d → EOF
            if event.ctrl and event.char == "d":
                sys.stdout.write("\n")
                sys.stdout.flush()
                raise EOFError

            # ctrl+c → exit
            if event.ctrl and event.char == "c":
                sys.stdout.write("\n")
                sys.stdout.flush()
                raise KeyboardInterrupt

            # registered bindings
            if handler.dispatch(event):
                continue

            # enter → submit
            if event.char == "enter":
                line = "".join(buf)
                sys.stdout.write("\n")
                sys.stdout.flush()
                if history is not None and line:
                    history.appendleft(line)
                return line

            # backspace
            if event.char == "backspace":
                if cursor_pos > 0:
                    buf.pop(cursor_pos - 1)
                    cursor_pos -= 1
                    _render("".join(buf), cursor_pos)
                continue

            # ctrl+u → clear line
            if event.ctrl and event.char == "u":
                buf.clear()
                cursor_pos = 0
                _render("", 0)
                continue

            # up arrow → history back
            if event.char == "up":
                if history:
                    if hist_idx == -1:
                        saved = "".join(buf)
                    if hist_idx < len(history) - 1:
                        hist_idx += 1
                        buf[:] = list(history[hist_idx])
                        cursor_pos = len(buf)
                        _render("".join(buf), cursor_pos)
                continue

            # down arrow → history forward
            if event.char == "down":
                if history:
                    if hist_idx > 0:
                        hist_idx -= 1
                        buf[:] = list(history[hist_idx])
                    elif hist_idx == 0:
                        hist_idx = -1
                        buf[:] = list(saved)
                    cursor_pos = len(buf)
                    _render("".join(buf), cursor_pos)
                continue

            # left → move cursor left
            if event.char == "left":
                if cursor_pos > 0:
                    cursor_pos -= 1
                    sys.stdout.write("\x1b[D")
                    sys.stdout.flush()
                continue

            # right → move cursor right
            if event.char == "right":
                if cursor_pos < len(buf):
                    cursor_pos += 1
                    sys.stdout.write("\x1b[C")
                    sys.stdout.flush()
                continue

            # alt+backspace → delete word left
            if event.char == "alt_backspace":
                end = cursor_pos
                while cursor_pos > 0 and buf[cursor_pos - 1] == " ":
                    cursor_pos -= 1
                while cursor_pos > 0 and buf[cursor_pos - 1] != " ":
                    cursor_pos -= 1
                del buf[cursor_pos:end]
                _render("".join(buf), cursor_pos)
                continue

            # alt+left → jump word left
            if event.char == "alt_left":
                while cursor_pos > 0 and buf[cursor_pos - 1] == " ":
                    cursor_pos -= 1
                while cursor_pos > 0 and buf[cursor_pos - 1] != " ":
                    cursor_pos -= 1
                _render("".join(buf), cursor_pos)
                continue

            # alt+right → jump word right
            if event.char == "alt_right":
                while cursor_pos < len(buf) and buf[cursor_pos] == " ":
                    cursor_pos += 1
                while cursor_pos < len(buf) and buf[cursor_pos] != " ":
                    cursor_pos += 1
                _render("".join(buf), cursor_pos)
                continue

            # skip other control/escape sequences
            if event.ctrl or event.escape:
                continue

            # printable char — insert at cursor
            buf.insert(cursor_pos, event.char)
            cursor_pos += 1
            _render("".join(buf), cursor_pos)

    return "".join(buf)
