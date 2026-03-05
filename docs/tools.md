# Tools Reference

Built-in tools in `nkd_agents/tools.py` and `nkd_agents/web.py`.

---

## `read_file(path: str)`

Read and return file contents. Anthropic-specific: returns rich content blocks for images and PDFs.

**Args**:
- `path`: Absolute or relative (to `cwd_ctx`) path

**Returns**: 
- Text files → string
- Images (jpg/jpeg/png/gif/webp) → Anthropic `image` content block (base64)
- PDFs → Anthropic `document` content block (base64)
- Error → error string

**Example**:
```python
result = await read_file("README.md")
result = await read_file("/abs/path/to/image.png")
```

---

## `edit_file(path, old_str, new_str, count=1)`

Create or edit a file.

**Args**:
- `path`: File path (absolute or relative to `cwd_ctx`)
- `old_str`: String to find. Use `"create_file"` to create a new file.
- `new_str`: Replacement string (or full file content for creation)
- `count`: Max occurrences to replace. `-1` = all. Default: `1`.

**Returns**: Success or error string.

**Behavior**:
- Creates parent directories automatically
- Displays colorized diff in logs
- On creation: writes `new_str` as the entire file content
- `old_str == new_str` → error (no-op guard)

**Example**:
```python
# Create
await edit_file("src/new.py", "create_file", "print('hello')")

# Edit
await edit_file("config.py", 'DEBUG = False', 'DEBUG = True')

# Replace all occurrences
await edit_file("file.txt", "old", "new", count=-1)
```

---

## `bash(command: str, timeout: int = 30)`

Execute a shell command.

**Args**:
- `command`: Shell command string
- `timeout`: Seconds before timeout. Default: `30`.

**Returns**: `"STDOUT:\n...\nSTDERR:\n...\nEXIT CODE: N"` or error string.

**Notes**:
- Runs with `cwd_ctx` as working directory
- Process killed on timeout or cancellation
- `asyncio.CancelledError` re-raised (not caught)

**Example**:
```python
result = await bash("git status")
result = await bash("pytest tests/", timeout=120)
```

---

## `subtask(prompt, task_label, model)`

Spawn an independent sub-agent with its own agentic loop.

**Args**:
- `prompt`: Full task description with context, expected output, constraints
- `task_label`: Short 3-5 word label for log tracking
- `model`: `"haiku"` or `"sonnet"`

**Returns**: Summary string from the sub-agent.

**Notes**:
- Sub-agent gets: `read_file`, `edit_file`, `bash`, and (if installed) `fetch_url`, `web_search`
- Sub-agent does NOT get `subtask` (no recursion)
- Inherits `anthropic_client_ctx` and `cwd_ctx` from parent
- Model map: `haiku` → `claude-haiku-4-6`, `sonnet` → `claude-sonnet-4-6`
- `anthropic_client_ctx` must be set or this raises immediately

**Example**:
```python
result = await subtask(
    "Refactor nkd_agents/utils.py to add dict support. Run tests after.",
    "add dict support",
    "sonnet"
)
```

---

## `web_search(query: str, max_results: int = 5)`

Search the web via DuckDuckGo. Requires `[cli]` extras (`playwright`).

**Args**:
- `query`: Search query
- `max_results`: Max results to return. Default: `5`.

**Returns**: Formatted string with title, URL, snippet per result.

**Notes**:
- Launches headless Chromium via Playwright
- Uses DuckDuckGo (`duckduckgo.com/?q=...`)
- Waits for `article` selector (10s timeout)

---

## `fetch_url(url: str, save_path: str)`

Fetch a URL and save as markdown. Requires `[cli]` extras (`httpx`, `trafilatura`).

**Args**:
- `url`: URL to fetch
- `save_path`: Where to save extracted markdown (relative to `cwd_ctx`)

**Returns**: `"Saved N chars to /path"` or error string.

**Notes**:
- Uses `trafilatura` for clean markdown extraction (no boilerplate)
- `favor_recall=True` means it tries to capture more content
- Creates parent directories automatically
- Does NOT return the content directly — use `bash` with grep/head to explore after

---

## Writing Custom Tools

Any `async` function with a docstring and type-annotated parameters works as a tool:

```python
async def get_weather(city: str, units: Literal["celsius", "fahrenheit"] = "celsius") -> str:
    """Get current weather for a city.
    
    Args:
        city: City name
        units: Temperature units
    """
    # implementation
    return f"72°F sunny in {city}"

result = await llm(client, [user("Weather in Paris?")], fns=[get_weather], ...)
```

**Rules**:
1. Must be `async`
2. Must have a docstring (used as tool description)
3. Parameters must use supported type annotations (`str`, `int`, `float`, `bool`, `list[T]`, `Literal[...]`, `T | None`)
4. Return `str` for text, or `list[Content]` for rich Anthropic content (images, etc.)
5. Handle errors internally — return error strings rather than raising
