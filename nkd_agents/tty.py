import asyncio
import codecs
import contextlib
import os
import shutil
import sys
import termios
import unicodedata
from collections.abc import AsyncGenerator, Callable, Iterator

ESC = "\x1b"
DIM, RESET = "\x1b[38;5;242m", "\x1b[0m"
PASTE_START, PASTE_END = "\x1b[200~", "\x1b[201~"


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
    new[3] &= ~(termios.ECHO | termios.ICANON | termios.ISIG | termios.IEXTEN)
    new[6][termios.VMIN], new[6][termios.VTIME] = 1, 0
    termios.tcsetattr(fd, termios.TCSANOW, new)
    write("\x1b[?2004h")  # paste on
    try:
        yield
    finally:
        write("\x1b[?2004l")  # paste off
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


async def keys() -> AsyncGenerator[str]:
    fd, q = sys.stdin.fileno(), asyncio.Queue[str]()
    dec = codecs.getincrementaldecoder("utf-8")("replace")
    loop = asyncio.get_running_loop()
    loop.add_reader(fd, lambda: q.put_nowait(dec.decode(os.read(fd, 4096))))
    try:
        with raw(fd):
            while True:
                yield await q.get()
    finally:
        loop.remove_reader(fd)


class TUI:
    def __init__(self, label: Callable[[], str] = lambda: "") -> None:
        self.buf = ""
        self.label = label

    def draw(self) -> None:
        cols = shutil.get_terminal_size().columns
        label = self.label().replace("\n", " ")
        text = self.buf.replace("\n", " ")
        used, start = sum(map(cell_width, label)), len(text)
        while start and used + cell_width(text[start - 1]) <= cols - 1:
            start -= 1
            used += cell_width(text[start])
        write(f"\r\x1b[K{DIM}{label}{RESET}{text[start:]}")

    def log(self, line: str) -> None:
        write("\r\x1b[K" + line.replace("\n", "\r\n") + "\r\n")
        self.draw()

    def paste(self, text: str) -> None:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.buf += "".join(c for c in text if c.isprintable() or c == "\n")

    async def input_loop(self, bindings: dict[str, Callable[[], None]]) -> None:
        self.draw()
        pasting = False
        async with contextlib.aclosing(keys()) as ks:
            async for s in ks:
                if pasting or s.startswith(PASTE_START):
                    text, end, s = s.removeprefix(PASTE_START).partition(PASTE_END)
                    self.paste(text)
                    pasting = not end
                if fn := bindings.get(s):
                    fn()
                elif not s.startswith(ESC):
                    for c in s:
                        if fn := bindings.get(c):
                            fn()
                        elif c.isprintable():
                            self.buf += c
                self.draw()
