import asyncio
import codecs
import contextlib
import os
import re
import shutil
import sys
import termios
from collections.abc import AsyncGenerator, Callable, Iterator


def write(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


@contextlib.contextmanager
def raw(fd: int) -> Iterator[None]:
    old = termios.tcgetattr(fd)
    new = termios.tcgetattr(fd)
    new[0] &= ~(termios.IXON | termios.ICRNL)
    new[3] &= ~(termios.ECHO | termios.ICANON | termios.IEXTEN)
    new[6][termios.VSUSP] = bytes([os.fpathconf(fd, "PC_VDISABLE")])
    new[6][termios.VMIN], new[6][termios.VTIME] = 1, 0
    termios.tcsetattr(fd, termios.TCSANOW, new)
    write("\x1b[?2004h")

    try:
        yield
    finally:
        write("\x1b[?2004l")

        termios.tcsetattr(fd, termios.TCSADRAIN, old)


TOKEN = re.compile(
    r"\x1b\[200~(?P<paste>.*?)\x1b\[201~|\x1b(?:\[[0-9;]*[@-~]|O?.)?|.", re.S
)


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    return "".join(c for c in text if c.isprintable() or c == "\n")


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
    try:
        with raw(fd):
            buf = ""
            while data := await q.get():
                buf += dec.decode(data)
                if (
                    buf.rfind("\x1b[200~") < buf.rfind("\x1b[201~")
                    or "\x1b[200~" not in buf
                ):
                    yield buf
                    buf = ""
            raise EOFError
    finally:
        loop.remove_reader(fd)


class TUI:
    def __init__(self, label: Callable[[], str] = lambda: "") -> None:
        self.buf = ""
        self.label = label

    def draw(self) -> None:
        cols = shutil.get_terminal_size().columns
        text = self.label() + self.buf.replace("\n", " ").replace("\t", " ")
        write("\r\x1b[K" + text[-(cols - 1) :])

    def write(self, s: str) -> None:
        write("\r\x1b[K" + s)
        self.draw()

    def flush(self) -> None:
        pass

    async def input_loop(self, on_key: Callable[[str], None]) -> None:
        self.draw()
        async with contextlib.aclosing(keys()) as ks:
            async for s in ks:
                for m in TOKEN.finditer(s):
                    if m["paste"] is not None:
                        self.buf += clean(m["paste"])
                    elif m[0].isprintable():
                        self.buf += m[0]
                    else:
                        on_key(m[0])
                self.draw()
