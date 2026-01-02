"""Retry utility with exponential backoff."""

import asyncio
import logging
import random
from typing import Any, Callable, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def with_retry(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
    **kwargs: Any,
) -> T:
    """
    Execute an async function with exponential backoff retry.

    Args:
        func: The async function to execute
        *args: Positional arguments to pass to func
        max_attempts: Maximum number of attempts (default 3)
        base_delay: Initial delay in seconds (default 1.0)
        max_delay: Maximum delay between retries (default 30.0)
        exceptions: Tuple of exception types to catch and retry
        **kwargs: Keyword arguments to pass to func

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries fail
    """
    last_exception: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_exception = e
            if attempt == max_attempts:
                logger.error(
                    f"All {max_attempts} attempts failed for {func.__name__}: {e}"
                )
                raise

            # Calculate delay with exponential backoff and jitter
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            # Add jitter (0-25% of delay)
            jitter = delay * random.uniform(0, 0.25)
            actual_delay = delay + jitter

            logger.warning(
                f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. "
                f"Retrying in {actual_delay:.2f}s..."
            )
            await asyncio.sleep(actual_delay)

    # This should never be reached, but satisfy type checker
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected retry loop exit")


def sync_with_retry(
    func: Callable[..., T],
    *args: Any,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple[Type[Exception], ...] = (Exception,),
    **kwargs: Any,
) -> T:
    """
    Execute a sync function with exponential backoff retry.

    Args:
        func: The sync function to execute
        *args: Positional arguments to pass to func
        max_attempts: Maximum number of attempts (default 3)
        base_delay: Initial delay in seconds (default 1.0)
        max_delay: Maximum delay between retries (default 30.0)
        exceptions: Tuple of exception types to catch and retry
        **kwargs: Keyword arguments to pass to func

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries fail
    """
    import time

    last_exception: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            last_exception = e
            if attempt == max_attempts:
                logger.error(
                    f"All {max_attempts} attempts failed for {func.__name__}: {e}"
                )
                raise

            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            jitter = delay * random.uniform(0, 0.25)
            actual_delay = delay + jitter

            logger.warning(
                f"Attempt {attempt}/{max_attempts} failed for {func.__name__}: {e}. "
                f"Retrying in {actual_delay:.2f}s..."
            )
            time.sleep(actual_delay)

    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected retry loop exit")
