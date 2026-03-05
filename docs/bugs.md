# Bugs

Tracked bugs, status, and fix notes.

---

## Active Bugs

### BUG-001: `nkd_agents/logging.py` shadows stdlib `logging`
**Severity**: High — breaks package import from its own directory  
**Status**: Open  
**File**: `nkd_agents/logging.py`  
**Description**: The module name collides with stdlib `logging`. Running from the package directory causes `AttributeError: partially initialized module 'logging' has no attribute 'Filter'` (circular import).  
**Fix**: Rename to `nkd_agents/log.py` and update all `from .logging import ...` references.  
**Affected files**: `anthropic.py`, `openai.py`, `tools.py`, `cli.py`, `utils.py`, `web.py`

---

### BUG-002: `cli.py` hard-imports `web` unconditionally
**Severity**: High — `nkd` CLI crashes without `[cli]` extras  
**Status**: Fixed  
**File**: `nkd_agents/cli.py:16`  
**Description**: `from .web import fetch_url, web_search` is at the top level. Without `playwright`/`trafilatura` installed, `nkd` crashes on launch.  
**Fix**: Wrapped in `try/except ImportError`, web tools excluded from TOOLS when import fails.

---

### BUG-003: `web.py` missing `httpx` in `[cli]` extras
**Severity**: Medium — runtime crash if httpx not present  
**Status**: Fixed  
**File**: `pyproject.toml`  
**Description**: `web.py` imports `httpx` for `fetch_url`, but `httpx` was not listed in `[project.optional-dependencies].cli`.  
**Fix**: Added `httpx>=0.27.0,<1.0.0` to `[cli]` extras in `pyproject.toml`.

---

### BUG-004: `fetch_url` return string has unbalanced parenthesis
**Severity**: Low — cosmetic, slightly confusing tool output  
**Status**: Fixed  
**File**: `nkd_agents/web.py:102`  
**Description**: Return string ended with `explore)` — stray `)` with no matching `(`.  
**Fix**: Changed to period.

---

### BUG-005: `anthropic.py` prompt cache mutation uses `# type: ignore`
**Severity**: Low — type safety hole  
**Status**: Fixed  
**File**: `nkd_agents/anthropic.py`  
**Description**: Cache control was mutated directly onto a TypedDict content block with `# type: ignore`. Empty content lists would raise `IndexError`. Thinking blocks (`ThinkingBlockParam`) don't support `cache_control`.  
**Fix**: Extracted `_ephemeral_cache(input)` context manager that finds the last `type="text"` block, sets `CacheControlEphemeralParam(type="ephemeral")` with proper type, and restores on exit. Guards against empty/non-dict/non-text blocks.

---

### BUG-006: `openai.py` appends `resp.output` with `# type: ignore`
**Severity**: Low — type safety hole  
**Status**: Open  
**File**: `nkd_agents/openai.py:125`  
**Description**: `input += resp.output` uses `# type: ignore` because `resp.output` items aren't typed as `ResponseInputItemParam`.  
**Fix**: Cast or map `resp.output` items through a proper converter.

---

### BUG-007: `tools.py:subtask` hardcodes model version suffix
**Severity**: Medium — silent breakage on model rename  
**Status**: Open  
**File**: `nkd_agents/tools.py`  
**Description**: `models = {"haiku": "claude-haiku-4-6", "sonnet": "claude-sonnet-4-6"}` hardcodes version. Any model rename breaks at runtime with no clear error.  
**Fix**: Use a lookup dict at module level (already done partially), but add a fallback or expose as a config point.

---

## Fixed Bugs

*(None yet — this tracker is new)*

---

## Bug Report Template

```
### BUG-NNN: Short description
**Severity**: High | Medium | Low
**Status**: Open | In Progress | Fixed
**File**: path/to/file.py:line
**Description**: What is wrong.
**Fix**: How to fix it.
```
