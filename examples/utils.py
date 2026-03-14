"""Utilities for example tests."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, Callable

from nkd_agents.log import GREEN, RESET, configure_logging, logging_ctx
from nkd_agents.utils import load_env

logger = logging.getLogger(__name__)


def test(
    test_name: str,
) -> Callable[[Callable[..., Coroutine[Any, Any, None]]], Callable[..., None]]:
    """Decorator that sets up test environment and handles errors."""

    def decorator(
        func: Callable[..., Coroutine[Any, Any, None]],
    ) -> Callable[..., None]:
        def wrapper(*args: Any, **kwargs: Any) -> None:
            load_env()
            configure_logging()
            logging_ctx.set({"test": test_name})

            asyncio.run(func(*args, **kwargs))
            logger.info(f"{GREEN}✓ Test passed!{RESET}")
            return None

        return wrapper

    return decorator
