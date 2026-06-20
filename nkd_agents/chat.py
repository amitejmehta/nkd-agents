import sys
import termios
import tty

CTRL_C = "\x03"
CTRL_L = "\x0c"
ENTER = "\r"
BACKSPACE = "\x7f"


def read_key():
    return sys.stdin.read(1)


def chat_input(prompt="> "):
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)

    buf = []

    try:
        tty.setraw(fd)
        sys.stdout.write(prompt)
        sys.stdout.flush()

        while True:
            ch = read_key()

            if ch == ENTER:
                sys.stdout.write("\r\n")
                return "".join(buf)

            elif ch == CTRL_C:
                raise KeyboardInterrupt

            elif ch == CTRL_L:
                # Ctrl-L clears current line
                sys.stdout.write("\r\033[K" + prompt)
                sys.stdout.write("".join(buf))
                sys.stdout.flush()

            elif ch == BACKSPACE:
                if buf:
                    buf.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()

            elif ch == "\x1b":
                # Escape sequences, e.g. arrows
                seq = sys.stdin.read(2)
                if seq == "[A":
                    # Up arrow
                    pass
                elif seq == "[B":
                    # Down arrow
                    pass

            elif ch.isprintable():
                buf.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()

    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


if __name__ == "__main__":
    while True:
        msg = chat_input("you> ")
        print("sent:", msg)
