# Todo

## Bugs (priority order)

1. Fix type-ignore hacks on cache_control mutation (anthropic.py + cli.py)
3. Fix type-ignore on `resp.output` append in openai.py

## Features / improvements

- `install.sh` curl script: point GitHub raw URL once repo is public (placeholder URL in script)

- OpenAI subtask equivalent
- Cancellation test for OpenAI provider (Anthropic has one, OpenAI doesn't)
- Vertex AI example
- `cwd_ctx` settable from CLI args (currently always `Path.cwd()` at import time)
- Skills prompt buffer label should show which skill is loaded
- `web_search` max_results tunable from CLI settings (currently hardcoded default of 5)
