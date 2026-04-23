# Tools

All CLI tools live in `nkd_agents/tools.py` and `nkd_agents/web.py`. They are plain async functions. The framework converts them to tool schemas automatically.

---

## `read_file`

```python
async def read_file(path: str) -> str | list[Content]
```

Read and return the contents of a file. Supports:

| Extension | Handling |
|-----------|----------|
| `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` | Base64-encoded, returned as `image` content block |
| `.pdf` | Base64-encoded, returned as `document` content block |
| Everything else | UTF-8 decoded, returned as `text` content block |

- `path` can be absolute or relative. Relative paths resolve against `cwd_ctx` (default: `Path.cwd()`).
- For text files the model sees the raw text. For images and PDFs the model receives the actual binary content (vision / document understanding).
- Logs the resolved path at INFO level.

---

## `write_file`

```python
async def write_file(path: str, content: str) -> str
```

Create a new file. Fails if the file already exists — use `edit_file` to modify existing files.

- Parent directories are created automatically.
- Returns `"Success: Created {path}"` or raises `ValueError` if the file already exists.

---

## `edit_file`

```python
async def edit_file(path: str, mode: Literal["insert", "replace"], new_str: str, old_str: str | None = None, count: int = 1, position: int | None = None) -> str
```

Edit an existing file. Fails if the file does not exist.

### Insert mode

Inserts `new_str` at a character offset within the file:

| `position` | Effect |
|------------|--------|
| `0` | Insert at the beginning |
| `N` | Insert after character N |
| `-1` or omitted | Append to the end |

### Replace mode

Replaces occurrences of `old_str` with `new_str`. Set `count=-1` to replace all occurrences.

### Return values

| Return | Meaning |
|--------|---------|
| `"Success: Updated {path}"` | Write succeeded |
| `ValueError("old_str not found in file content")` | String not present in file |
| `ValueError("old_str and new_str must be different")` | No-op guard |
| `ValueError("File '{path}' not found")` | File doesn't exist |
| `ValueError("old_str is required for replace mode")` | Missing param |

### Diff display

Before writing, `display_diff()` prints a colorized unified diff to stderr.

### Best practice

For multiple changes to the same file, call `edit_file` multiple times with small, targeted `old_str` values.

---

## `bash`

```python
async def bash(command: str, timeout: int = 30) -> str
```

Execute a shell command via `bash -c`. Returns:

```
STDOUT:
{stdout}
STDERR:
{stderr}
EXIT CODE: {returncode}
```

Or raises `TimeoutError("Command timed out after {timeout} seconds: {command}")` after `SIGKILL`-ing the process group. The framework's tool dispatcher surfaces the exception as an error string to the model.

- Runs in `cwd_ctx` directory.
- Default timeout: 30 seconds. Override per-call.

---

## `glob`

```python
async def glob(pattern: str, path: str | None = None, include_hidden: bool = False) -> str
```

List files matching a glob pattern, relative to `path` (or `cwd`).

- Fast file discovery without shelling out. Recursion via `**` is supported.
- Hidden files and directories (any path component starting with `.`) are excluded by default — set `include_hidden=True` to include them (e.g. to search `.venv` or `.git`).
- Returns a newline-separated list of matching paths (relative to the search dir), or `"No matches found"`.

---

## `grep`

```python
async def grep(pattern: str, include: str | None = None, path: str | None = None, context: int = 2, include_hidden: bool = False) -> str
```

Search file contents using ripgrep (`rg`).

- Hidden files and directories are excluded by default — set `include_hidden=True` to search them (e.g. inside `.venv` or `.git`).
- `include`: optional glob to filter files (e.g. `'*.py'`, `'*.ts'`).
- `context`: lines of context around each match (default: 2).
- Returns ripgrep output with file paths, line numbers, and context. Truncated to 200 matches.

---

## `web_search`

```python
async def web_search(query: str, max_results: int = 5) -> str
```

Search the web using DuckDuckGo via headless Chromium (Playwright).

Returns formatted results:
```
Title: {title}
URL: {url}
Snippet: {snippet}

Title: ...
```

Or `"No results found"`.

- Requires `pip install nkd_agents[cli,web]` (installs `playwright`).
- Requires `playwright install chromium` (or `chrome` channel — uses Chrome if available).
- Uses a realistic User-Agent to avoid bot detection.
- Waits for `article` elements with a 10-second timeout.
- `max_results` caps how many DuckDuckGo result cards are returned.

---

## `fetch_url`

```python
async def fetch_url(url: str, save_path: str) -> str
```

Fetch a webpage, extract clean content with Trafilatura, save as markdown to disk.

Returns `"Saved {N:,} chars to {path}. For long files, start by grepping for keywords."` or an error string.

- Uses `httpx` for the HTTP request (follows redirects, 30s timeout).
- `trafilatura.extract()` with `output_format="markdown"`, `include_tables=True`, `favor_recall=True`.
- `save_path` resolves relative to `cwd_ctx`.
- Parent directories created automatically.
- **Does not return the content directly.** Saves to disk and returns the path. The model then uses `bash` (grep/head/tail/cat) to read only the relevant parts. This keeps large documents out of context until actually needed — critical for deep research sessions.

---

## Writing Custom Tools

Any async function with a docstring and typed parameters works:

```python
async def get_stock_price(ticker: str) -> str:
    """Get the current stock price for a ticker symbol."""
    price = await some_api(ticker)
    return f"{ticker}: ${price:.2f}"

response = await agent(client, messages, fns=[get_stock_price], **kwargs)
```

Rules:
- Must be `async`.
- Must have a docstring (description shown to the model).
- Parameters must use supported types: `str`, `int`, `float`, `bool`, `Literal[...]`, `T | None`.
- Return `str` for plain text. For rich content (images, PDFs, mixed blocks) return `FileContent` (`nkd_agents.tools.FileContent` — a frozen dataclass with `data: bytes` and `ext: str`; each provider converts it to its own content format) or `ResponseFunctionCallOutputItemListParam` (OpenAI).
- Raise `ValueError` for user-facing errors (bad args, missing files, etc).