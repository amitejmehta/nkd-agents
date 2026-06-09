"""Minimal Chrome DevTools Protocol (CDP) client over a hand-rolled WebSocket.

Zero dependencies beyond the stdlib. Speaks raw RFC 6455 frames — no playwright,
no websockets library. ~40 lines.

Usage::

    response = await cdp(host, port, ws_path, {"id": 1, "method": "Runtime.evaluate", ...})
"""

import asyncio
import base64
import json
import re
import secrets
import shutil
import struct
from html.parser import HTMLParser
from pathlib import Path

# ---------------------------------------------------------------------------
# WebSocket connection helpers and Chrome binary finder
# ---------------------------------------------------------------------------

_CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
]


async def _ws_connect(host: str, port: int, path: str):
    """Open a raw WebSocket connection. Returns (reader, writer)."""
    reader, writer = await asyncio.open_connection(host, port)
    key = base64.b64encode(secrets.token_bytes(16)).decode()
    writer.write(
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n".encode()
    )
    await writer.drain()
    while await reader.readline() not in (b"\r\n", b"\n", b""):
        pass
    return reader, writer


async def _ws_send(writer: asyncio.StreamWriter, payload: dict) -> None:
    data = json.dumps(payload).encode()
    mask = secrets.token_bytes(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
    length = len(data)
    header = (
        struct.pack("BB", 0x81, 0x80 | length)
        if length < 126
        else struct.pack("!BBH", 0x81, 0xFE, length)
    )
    writer.write(header + mask + masked)
    await writer.drain()


async def _ws_recv(reader: asyncio.StreamReader) -> dict:
    header = await reader.readexactly(2)
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await reader.readexactly(8))[0]
    return json.loads(await reader.readexactly(length))


async def cdp(host: str, port: int, ws_path: str, cmd: dict) -> dict:
    """Send a single CDP command and return the matching response."""
    reader, writer = await _ws_connect(host, port, ws_path)
    try:
        await _ws_send(writer, cmd)
        while True:
            msg = await asyncio.wait_for(_ws_recv(reader), timeout=15)
            if msg.get("id") == cmd["id"]:
                return msg
    finally:
        writer.close()


def find_chrome() -> str:
    for candidate in _CHROME_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
        found = shutil.which(candidate)
        if found:
            return found
    raise RuntimeError(
        "Chrome not found. Install Google Chrome or Chromium to use web_search."
    )


# ---------------------------------------------------------------------------
# HTML → Markdown Parser
# ---------------------------------------------------------------------------

_SKIP_TAGS = frozenset(
    [
        "script",
        "style",
        "noscript",
        "iframe",
        "svg",
        "form",
        "button",
        # boilerplate zones
        "nav",
        "aside",
        "footer",
        "header",
        "menu",
        "dialog",
        "select",
        "option",
        "label",
        "input",
        "textarea",
        # media / captions — alt text leaks dangling brackets
        "figure",
        "figcaption",
        "picture",
        # footnote references — [1], [2] etc. add noise
        "sup",
        "sub",
        # math markup — MathML emits noisy fragments
        "math",
    ]
)

# Semantic main-content landmark tags — if any exist, restrict extraction to them
_MAIN_TAGS = frozenset(["article", "main"])

# Void elements: no closing tag, so never push to skip_depth
_VOID_TAGS = frozenset(
    [
        "meta",
        "link",
        "br",
        "hr",
        "img",
        "input",
        "area",
        "base",
        "col",
        "embed",
        "param",
        "source",
        "track",
        "wbr",
    ]
)

_BLOCK_TAGS = frozenset(
    [
        "p",
        "div",
        "section",
        "article",
        "blockquote",
        "dt",
        "dd",
    ]
)

_HEADING_TAGS = {
    "h1": "#",
    "h2": "##",
    "h3": "###",
    "h4": "####",
    "h5": "#####",
    "h6": "######",
}

# CSS classes / roles on div/section/table that indicate boilerplate to skip
_SKIP_CLASS_RE = re.compile(
    r"\bnavbox\b|"
    r"\bsidebar\b|"
    r"\binfobox\b|"
    r"\bprintfooter\b|"
    r"\bmw-jump-link\b|"
    r"\bmw-editsection\b|"
    r"\bcatlinks\b|"
    r"\breflist\b|"
    r"\breferences\b|"
    r"\bexternal.?links?\b|"
    r"\bnoprint\b",
    re.IGNORECASE,
)
_SKIP_ROLE_RE = re.compile(r"^(navigation|complementary|note)$", re.IGNORECASE)

# href patterns whose links should be silently dropped (text still emitted)
_NOISE_HREF_RE = re.compile(
    r"^#cite_note|"  # footnote back-refs  [[1]](#cite_note-1)
    r"^#cite_ref|"  # footnote forward-refs
    r"Wikipedia:Citation_needed|"  # [citation needed]
    r"Wikipedia:Please_clarify|"
    r"#editSection|"  # MediaWiki inline edit links
    r"action=edit",  # any edit-action URL
    re.IGNORECASE,
)

# link *text* patterns that are purely navigational noise
_NOISE_LINK_TEXT_RE = re.compile(r"^\s*\[edit\]\s*$", re.IGNORECASE)


def _has_main_zone(html: str) -> bool:
    """Quick scan: does this HTML contain an <article> or <main> tag?"""
    return bool(re.search(r"<(article|main)[\s>]", html, re.IGNORECASE))


def _extract_title(html: str) -> str:
    """Return the bare page title (strips ' - Site Name' suffixes)."""
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    if not m:
        return ""
    title = m.group(1).strip()
    # Strip common " - Site Name" / " | Site Name" suffixes
    title = re.sub(r"\s*[-–|]\s*[^-–|]{3,}$", "", title).strip()
    return title


class ContentExtractor(HTMLParser):
    def __init__(self, restrict_to_main: bool = False, title: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._parts: list[str] = []
        self._tag_stack: list[str] = []
        self._in_pre = False
        self._in_cell = False
        self._cell_buf: list[str] = []
        self._row_cells: list[str] = []
        self._in_thead = False
        self._restrict_to_main = restrict_to_main
        self._main_depth = 0  # >0 means we're inside a main/article zone
        self._outer_skip_depth = 0  # saved skip_depth when entering main zone
        # link state
        self._in_link = False  # True when inside any <a>
        self._link_suppress = False  # True when the href is noise (emit text only)
        self._link_text_buf: list[str] = []
        if title:
            self._parts.append(f"# {title}\n\n")

    def _is_active(self) -> bool:
        """True when content should be emitted (not skipped, in main zone if restricted)."""
        return not self._skip_depth and (
            not self._restrict_to_main or self._main_depth > 0
        )

    def handle_starttag(self, tag: str, attrs: list) -> None:
        # Void elements: handle inline effects only, never touch skip_depth / tag_stack
        if tag in _VOID_TAGS:
            if self._is_active():
                if tag == "br":
                    self._parts.append("\n")
                elif tag == "hr":
                    self._parts.append("\n---\n")
            return

        # main-zone tracking: entering a main/article zone resets skip depth
        # (the main zone may be nested inside skipped outer containers)
        if tag in _MAIN_TAGS:
            self._main_depth += 1
            self._tag_stack.append(tag)
            # Suspend any outer skip so inner content is active
            self._outer_skip_depth = self._skip_depth
            self._skip_depth = 0
            return

        # Always push to stack so handle_endtag can match depth correctly
        self._tag_stack.append(tag)

        # Determine if this tag's subtree should be skipped
        should_skip = (
            self._skip_depth > 0
            or (self._restrict_to_main and self._main_depth == 0)
            or tag in _SKIP_TAGS
        )
        if not should_skip and tag in ("div", "section", "table", "span"):
            attr_map = dict(attrs)
            cls = attr_map.get("class", "")
            role = attr_map.get("role", "")
            if _SKIP_CLASS_RE.search(cls) or _SKIP_ROLE_RE.match(role):
                should_skip = True

        if should_skip:
            self._skip_depth += 1
            return

        # Active content — emit markdown effects
        if tag == "pre":
            self._in_pre = True
            self._parts.append("\n```\n")
        elif tag == "code" and not self._in_pre:
            self._parts.append("`")
        elif tag in _HEADING_TAGS:
            self._parts.append(f"\n{_HEADING_TAGS[tag]} ")
        elif tag in ("td", "th"):
            self._in_cell = True
            self._cell_buf = []
        elif tag == "li":
            self._parts.append("\n- ")
        elif tag == "thead":
            self._in_thead = True
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")
        elif tag == "a":
            attr_map = dict(attrs)
            href = attr_map.get("href", "")
            self._in_link = True
            self._link_text_buf = []
            if href and not _NOISE_HREF_RE.search(href):
                self._link_suppress = False
                self._parts.append("\x00LINKSTART\x00")
                self._tag_stack[-1] = f"a:{href}"
            else:
                self._link_suppress = True

    def handle_endtag(self, tag: str) -> None:
        # Void elements never push to tag_stack — ignore spurious end events
        if tag in _VOID_TAGS:
            return

        if tag in _MAIN_TAGS:
            if self._main_depth > 0:
                self._main_depth -= 1
            # Restore outer skip depth if we fully exited main zones
            if self._main_depth == 0:
                self._skip_depth = self._outer_skip_depth
                self._outer_skip_depth = 0
            if self._tag_stack:
                self._tag_stack.pop()
            return

        current = self._tag_stack.pop() if self._tag_stack else tag

        if self._skip_depth:
            # This tag was inside a skipped subtree
            self._skip_depth -= 1
            return

        # Active close — emit markdown effects
        if tag == "pre":
            self._in_pre = False
            self._parts.append("\n```\n")
        elif tag == "code" and not self._in_pre:
            self._parts.append("`")
        elif tag in ("td", "th"):
            self._in_cell = False
            self._row_cells.append("".join(self._cell_buf).strip())
            self._cell_buf = []
        elif tag == "tr":
            if self._row_cells:
                self._parts.append("\n| " + " | ".join(self._row_cells) + " |")
                self._row_cells = []
        elif tag == "thead":
            last_row = next(
                (p for p in reversed(self._parts) if p.startswith("\n| ")), None
            )
            ncols = last_row.strip().strip("|").count("|") + 1 if last_row else 1
            self._parts.append("\n| " + " | ".join(["---"] * ncols) + " |")
            self._in_thead = False
        elif tag == "table":
            self._parts.append("\n")
        elif tag in _HEADING_TAGS or tag in _BLOCK_TAGS:
            self._parts.append("\n")
        elif tag == "a":
            self._in_link = False
            link_text = "".join(self._link_text_buf)
            self._link_text_buf = []
            if self._link_suppress:
                if not _NOISE_LINK_TEXT_RE.match(link_text):
                    if self._in_cell:
                        self._cell_buf.append(link_text)
                    else:
                        self._parts.append(link_text)
                self._link_suppress = False
            elif current.startswith("a:"):
                href = current[2:]
                if _NOISE_LINK_TEXT_RE.match(link_text):
                    idx = len(self._parts) - 1
                    while idx >= 0 and self._parts[idx] != "\x00LINKSTART\x00":
                        idx -= 1
                    if idx >= 0:
                        self._parts[idx : idx + 1] = []
                else:
                    idx = len(self._parts) - 1
                    while idx >= 0 and self._parts[idx] != "\x00LINKSTART\x00":
                        idx -= 1
                    if idx >= 0:
                        self._parts[idx] = f"[{link_text}]({href})"

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_link:
            # Buffer all text inside <a>…</a> (including nested tags like <i>, <b>)
            self._link_text_buf.append(data)
            return
        if self._in_cell:
            self._cell_buf.append(data)
        else:
            self._parts.append(data)

    def get_markdown(self) -> str:
        text = "".join(self._parts)
        # Remove any leftover sentinels (unclosed links)
        text = text.replace("\x00LINKSTART\x00", "")
        # Strip Wikipedia [edit] section links that weren't caught as <a> (bare text)
        text = re.sub(r"\s*\[edit\]", "", text)
        # Remove lines that are purely whitespace (tabs/spaces from HTML indentation)
        text = re.sub(r"^[ \t]+$", "", text, flags=re.MULTILINE)
        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_markdown(html: str) -> str:
    """Extract main content from HTML as Markdown.

    Automatically restricts to <article>/<main> zones when present,
    falling back to full-page extraction otherwise.
    """
    restrict = _has_main_zone(html)
    title = _extract_title(html)
    extractor = ContentExtractor(restrict_to_main=restrict, title=title)
    extractor.feed(html)
    return extractor.get_markdown()
