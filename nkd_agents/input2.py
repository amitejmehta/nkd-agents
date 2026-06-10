"""Minimal raw-terminal input module.

Layers:
  KeyEvent        — parsed keystroke
  RawTerminal     — context manager; owns raw mode; yields KeyEvents
  LineState       — mutable line-editor state
  LINE_ACTIONS    — dict of key → action(LineState); composable, extensible
  readline_input  — async line reader: wires it all together

Example:
    from nkd_agents.input2 import readline_input, Interrupt
    from collections import deque

    history = deque(maxlen=1000)
    bindings = {"\x1b": my_interrupt_fn}

    async def loop():
        while True:
            try:
                line = await readline_input("> ", bindings=bindings, history=history)
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

    def __str__(self) -> str:
        return f"{'ctrl+' if self.ctrl else ''}{self.char!r}"


def _parse(data: bytes) -> KeyEvent:
    if data == b"\x1b":
        return KeyEvent(char="esc")
    if data == b"\x1b[A":
        return KeyEvent(char="up")
    if data == b"\x1b[B":
        return KeyEvent(char="down")
    if data == b"\x1b[C":
        return KeyEvent(char="right")
    if data == b"\x1b[D":
        return KeyEvent(char="left")
    if data in (b"\x1b[1;3C", b"\x1bf", b"\x1b\x1b[C"):
        return KeyEvent(char="alt-right")
    if data in (b"\x1b[1;3D", b"\x1bb", b"\x1b\x1b[D"):
        return KeyEvent(char="alt-left")
    if data in (b"\x1b\x7f", b"\x1b[3;3~", b"\x17"):
        return KeyEvent(char="alt-backspace")
    if data == b"\x1b[Z":
        return KeyEvent(char="shift-tab")
    if len(data) == 1:
        b = data[0]
        if b == 0x7F:
            return KeyEvent(char="backspace")
        if b in (0x0D, 0x0A):
            return KeyEvent(char="enter")
        if b == 0x09:
            return KeyEvent(char="tab")
        if 0x01 <= b <= 0x1A:
            return KeyEvent(char=chr(b + 0x60), ctrl=True)
        return KeyEvent(char=data.decode("utf-8", errors="replace"))
    return KeyEvent(char=data.decode("utf-8", errors="replace"))


# ---------------------------------------------------------------------------
# RawTerminal
# ---------------------------------------------------------------------------


class RawTerminal:
    """Async context manager that owns raw mode; yields KeyEvents.

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
            data = await self._reader.read(4096)
            if not data:
                raise StopAsyncIteration
            return _parse(data)
        except asyncio.IncompleteReadError:
            raise StopAsyncIteration

    async def read_raw(self) -> bytes:
        """Read raw bytes (may contain multiple chars from a paste)."""
        if self._reader is None:
            return b""
        return await self._reader.read(4096)


# ---------------------------------------------------------------------------
# LineState
# ---------------------------------------------------------------------------

_CLEAR = "\r\033[K"


@dataclass
class LineState:
    buf: list[str] = field(default_factory=list)
    cursor_pos: int = 0
    hist_idx: int = -1  # -1 = live input
    saved: str = ""
    prompt: str = "> "
    history: deque[str] | None = None
    pastes: dict[int, str] = field(default_factory=dict)

    def render(self) -> None:
        line = "".join(self.buf)
        sys.stdout.write(f"{_CLEAR}{self.prompt}{line}")
        diff = len(line) - self.cursor_pos
        if diff:
            sys.stdout.write(f"\x1b[{diff}D")
        sys.stdout.flush()

    def insert(self, ch: str) -> None:
        self.buf.insert(self.cursor_pos, ch)
        self.cursor_pos += 1

    def insert_paste(self, text: str) -> None:
        n = len(self.pastes) + 1
        self.pastes[n] = text
        token = list(f"[paste #{n}]")
        self.buf[self.cursor_pos : self.cursor_pos] = token
        self.cursor_pos += len(token)

    def submit(self) -> str:
        line = "".join(self.buf)
        for n, text in self.pastes.items():
            line = line.replace(f"[paste #{n}]", text)
        sys.stdout.write("\n")
        sys.stdout.flush()
        if self.history is not None and line:
            self.history.appendleft(line)
        return line


# ---------------------------------------------------------------------------
# LineActions  (key → Callable[[LineState], None])
# ---------------------------------------------------------------------------

LineAction = Callable[[LineState], None]


def _backspace(s: LineState) -> None:
    if s.cursor_pos > 0:
        s.buf.pop(s.cursor_pos - 1)
        s.cursor_pos -= 1
        s.render()


def _clear_line(s: LineState) -> None:
    s.buf.clear()
    s.cursor_pos = 0
    s.render()


def _left(s: LineState) -> None:
    if s.cursor_pos > 0:
        s.cursor_pos -= 1
        sys.stdout.write("\x1b[D")
        sys.stdout.flush()


def _right(s: LineState) -> None:
    if s.cursor_pos < len(s.buf):
        s.cursor_pos += 1
        sys.stdout.write("\x1b[C")
        sys.stdout.flush()


def _word_left(s: LineState) -> None:
    while s.cursor_pos > 0 and s.buf[s.cursor_pos - 1] == " ":
        s.cursor_pos -= 1
    while s.cursor_pos > 0 and s.buf[s.cursor_pos - 1] != " ":
        s.cursor_pos -= 1
    s.render()


def _word_right(s: LineState) -> None:
    while s.cursor_pos < len(s.buf) and s.buf[s.cursor_pos] == " ":
        s.cursor_pos += 1
    while s.cursor_pos < len(s.buf) and s.buf[s.cursor_pos] != " ":
        s.cursor_pos += 1
    s.render()


def _word_backspace(s: LineState) -> None:
    end = s.cursor_pos
    while s.cursor_pos > 0 and s.buf[s.cursor_pos - 1] == " ":
        s.cursor_pos -= 1
    while s.cursor_pos > 0 and s.buf[s.cursor_pos - 1] != " ":
        s.cursor_pos -= 1
    del s.buf[s.cursor_pos : end]
    s.render()


def _hist_up(s: LineState) -> None:
    if not s.history:
        return
    if s.hist_idx == -1:
        s.saved = "".join(s.buf)
    if s.hist_idx < len(s.history) - 1:
        s.hist_idx += 1
        s.buf[:] = list(s.history[s.hist_idx])
        s.cursor_pos = len(s.buf)
        s.render()


def _hist_down(s: LineState) -> None:
    if not s.history or s.hist_idx == -1:
        return
    if s.hist_idx > 0:
        s.hist_idx -= 1
        s.buf[:] = list(s.history[s.hist_idx])
    else:
        s.hist_idx = -1
        s.buf[:] = list(s.saved)
    s.cursor_pos = len(s.buf)
    s.render()


# Default built-in actions. Keyed by KeyEvent.char.
LINE_ACTIONS: dict[str, LineAction] = {
    "backspace": _backspace,
    "ctrl+u": _clear_line,
    "left": _left,
    "right": _right,
    "alt-left": _word_left,
    "alt-right": _word_right,
    "alt-backspace": _word_backspace,
    "up": _hist_up,
    "down": _hist_down,
}


# ---------------------------------------------------------------------------
# readline_input
# ---------------------------------------------------------------------------


async def readline_input(
    prompt: str = "> ",
    *,
    bindings: dict[str, Callable[[], None]] | None = None,
    history: deque[str] | None = None,
) -> str:
    """Async line reader. Returns completed line.
    Raises Interrupt on interrupt binding, EOFError on ctrl+d, KeyboardInterrupt on ctrl+c.
    """
    bindings = bindings or {}
    state = LineState(prompt=prompt, history=history)
    state.render()

    async with RawTerminal() as term:
        while True:
            data = await term.read_raw()
            if not data:
                break

            # Multi-byte chunk → treat as paste: store and show token, render once.
            text = data.decode("utf-8", errors="replace")
            if len(text) > 1:
                state.insert_paste(text)
                state.render()
                continue

            event = _parse(data)

            # ctrl+d → EOF
            if event.ctrl and event.char == "d":
                sys.stdout.write("\n")
                sys.stdout.flush()
                raise EOFError

            # user bindings
            if event.char in bindings:
                bindings[event.char]()
                continue

            # enter → submit
            if event.char == "enter":
                return state.submit()

            # built-in line actions
            action_key = f"ctrl+{event.char}" if event.ctrl else event.char
            action = LINE_ACTIONS.get(action_key)
            if action:
                action(state)
                continue

            # printable char
            if not event.ctrl and len(event.char) == 1:
                state.insert(event.char)
                state.render()

    return "".join(state.buf)
