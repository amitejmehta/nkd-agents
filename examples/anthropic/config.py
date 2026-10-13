"""Shared client and model settings for Anthropic examples."""

import os

KWARGS = {"model": os.getenv("MODEL", "claude-haiku-5-5"), "max_tokens": 4096}
