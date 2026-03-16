# TODO

## Bugs

- `cache_control` mutation on `input[-1]["content"][-1]` assumes last content block is a dict — will break for non-dict content blocks. Needs a proper fix in `anthropic.py` and `cli.py` (two `# TODO: fix this` comments).

## Up next

- Fix `cache_control` mutation (see bug above)
- Update `CLAUDE.md` to reflect new doc structure (remove refs to `docs/` subdirectory, add `VISION.md` and `DROPPED.md`)
- `openai.py`: `input += resp.output` type ignore — investigate proper typing fix
