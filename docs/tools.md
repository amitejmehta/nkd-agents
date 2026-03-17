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

## `edit_file`

```python
async def edit_file(path: str, old_str: str, new_str: str, count: int = 1) -> str
```

Create a new file or replace text in an existing file.

### Creating a file

```
old_str = "create_file"
new_str = <full file contents>
```

Parent directories are created automatically.

### Editing a file

Replaces the first occurrence of `old_str` with `new_str`. Set `count=-1` to replace all occurrences.

### Return values

| Return | Meaning |
|--------|---------|
| `"Success: Updated {path}"` | Write succeeded |
| `"Error: old_str not found in file content"` | String not present in file |
| `"Error: old_str and new_str must be different"` | No-op guard |
| `"Error: File '{path}' not found"` | File doesn't exist (non-create mode) |
| `"Error editing file '{path}': {description}"` | Other I/O failure |

### Diff display

Before writing, `display_diff()` prints a colorized unified diff to stderr (green `+` lines, red `-` lines). This is always visible in the terminal regardless of log level.

### Best practice

For multiple changes to the same file, call `edit_file` multiple times with small, targeted `old_str` values rather than one large replacement. This minimises the chance of `old_str not found` errors and makes diffs readable.

---

## `bash`

```python
async def bash(command: str, timeout: int = 30, background: bool = False) -> str
```

Execute a shell command via `bash -c`. Returns:

```
STDOUT:
{stdout}
STDERR:
{stderr}
EXIT CODE: {returncode}
```

Or `"Background PID: {pid}"` (when `background=True`), `"Error: Command timed out after {timeout} seconds"`.

- Runs in `cwd_ctx` directory.
- Default timeout: 30 seconds. Override per-call.
- `background=True`: runs the process in the background, returning its PID immediately.
- The process is killed on timeout (`process.kill()` + `await process.wait()`).

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

- Requires `pip install nkd_agents[cli]` (installs `playwright`).
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

response = await llm(client, messages, fns=[get_stock_price], **kwargs)
```

Rules:
- Must be `async`.
- Must have a docstring (description shown to the model).
- Parameters must use supported types: `str`, `int`, `float`, `bool`, `Literal[...]`, `T | None`.
- Return `str` for text, or `list[Content]` for rich content (Anthropic) / `ResponseFunctionCallOutputItemListParam` (OpenAI).
- Catch your own exceptions and return descriptive error strings — don't let tools raise.
