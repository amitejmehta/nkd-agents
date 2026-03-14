# Known Bugs

## `subtask` model dict diverges from CLI `MODELS`

`tools.py` has `{"haiku": "claude-haiku-4-6", "sonnet": "claude-sonnet-4-6"}`. CLI has `MODELS = ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"]`. These are separate — a model version bump in one won't update the other.

## Type-ignore hacks on cache_control mutation

`anthropic.py:144/150` and `cli.py` cache warmer mutate `cache_control` onto message content blocks with `# type: ignore`. Needs proper typing.

## `openai.py:125` type-ignore on `resp.output` append

`input += resp.output` is typed with `# type: ignore`. Needs proper typing.

