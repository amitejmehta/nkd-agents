import asyncio
import codecs
import contextlib
import logging
import os
import re
import shutil
import sys
import termios
import unicodedata
from collections.abc import AsyncGenerator, Callable, Iterator


def write(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def cell_width(c: str) -> int:
    if unicodedata.combining(c):
        return 0
    return 2 if unicodedata.east_asian_width(c) in "WF" else 1


@contextlib.contextmanager
def raw(fd: int) -> Iterator[None]:
    old = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    new[0] &= ~(termios.IXON | termios.ICRNL)
    new[3] &= ~(termios.ECHO | termios.ICANON | termios.IEXTEN)
    new[6][termios.VMIN], new[6][termios.VTIME] = 1, 0
    termios.tcsetattr(fd, termios.TCSANOW, new)
    write("\x1b[?2004h")  # paste on

    try:
        yield
    finally:
        write("\x1b[?2004l")  # paste off

        termios.tcsetattr(fd, termios.TCSADRAIN, old)


TOKEN = re.compile(
    r"\x1b\[200~(?P<paste>.*?)\x1b\[201~|\x1b(?:\[[0-9;]*[@-~]|O?.)?|.", re.S
)


async def keys() -> AsyncGenerator[str]:
    fd, q = sys.stdin.fileno(), asyncio.Queue[bytes]()
    dec = codecs.getincrementaldecoder("utf-8")("replace")
    loop = asyncio.get_running_loop()

    def on_readable() -> None:
        try:
            q.put_nowait(os.read(fd, 4096))
        except OSError:
            q.put_nowait(b"")

    loop.add_reader(fd, on_readable)
    buf = ""
    try:
        with raw(fd):
            while True:
                data = await q.get()
                if not data:
                    raise EOFError
                buf += dec.decode(data)
                if (cut := buf.rfind("\x1b[200~")) <= buf.rfind("\x1b[201~"):
                    start = "\x1b[200~"
                    cut = len(buf) - next(
                        (n for n in range(5, 1, -1) if buf.endswith(start[:n])), 0
                    )
                if cut:
                    yield buf[:cut]
                    buf = buf[cut:]
    finally:
        loop.remove_reader(fd)


class TUI:
    def __init__(self, label: Callable[[], str] = lambda: "") -> None:
        self.buf = ""
        self.label = label

    def draw(self) -> None:
        cols = shutil.get_terminal_size().columns
        label = self.label().replace("\n", " ")
        text = self.buf.replace("\n", " ").replace("\t", " ")
        used, start = sum(map(cell_width, label)), len(text)
        while start and used + cell_width(text[start - 1]) <= cols - 1:
            start -= 1
            used += cell_width(text[start])
        write(f"\r\x1b[K{label}{text[start:]}")

    def log(self, line: str) -> None:
        write("\r\x1b[K" + line.replace("\n", "\r\n") + "\r\n")
        self.draw()

    def paste(self, text: str) -> None:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.buf += "".join(c for c in text if c.isprintable() or c in "\n\t")

    async def input_loop(self, bindings: dict[str, Callable[[], None]]) -> None:
        self.draw()
        async with contextlib.aclosing(keys()) as ks:
            async for s in ks:
                for m in TOKEN.finditer(s):
                    if m["paste"] is not None:
                        self.paste(m["paste"])
                    elif fn := bindings.get(m[0]):
                        fn()
                    elif m[0].isprintable():
                        self.buf += m[0]
                self.draw()


class TUIHandler(logging.Handler):
    def __init__(self, tui: TUI) -> None:
        super().__init__()
        self.tui = tui

    def emit(self, record: logging.LogRecord) -> None:
        self.tui.log(self.format(record))
