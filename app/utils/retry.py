"""
Retry utilities with exponential backoff for API calls.
"""

import time
from functools import wraps
from typing import Callable, TypeVar, Any

from openai import (
    APIError,
    APIConnectionError,
    RateLimitError,
    APITimeoutError,
)

from .logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# Exceptions that should trigger a retry
RETRYABLE_EXCEPTIONS = (
    APIConnectionError,
    RateLimitError,
    APITimeoutError,
    APIError,
)


def with_retry(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = RETRYABLE_EXCEPTIONS,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that adds retry logic with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay between retries
        exponential_base: Base for exponential backoff calculation
        retryable_exceptions: Tuple of exceptions that should trigger retry

    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            delay = initial_delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"All {max_retries} retries failed for {func.__name__}",
                            exc_info=True
                        )
                        raise

                    # Calculate delay with exponential backoff
                    sleep_time = min(delay, max_delay)

                    logger.warning(
                        f"Retry {attempt + 1}/{max_retries} for {func.__name__} "
                        f"after {sleep_time:.1f}s delay. Error: {type(e).__name__}: {e}"
                    )

                    time.sleep(sleep_time)
                    delay *= exponential_base

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError(f"Unexpected state in retry logic for {func.__name__}")

        return wrapper
    return decorator


def retry_on_rate_limit(func: Callable[..., T]) -> Callable[..., T]:
    """
    Convenience decorator specifically for rate limit handling.

    Uses more aggressive retry settings for rate limits.
    """
    return with_retry(
        max_retries=5,
        initial_delay=2.0,
        max_delay=120.0,
        exponential_base=2.0,
        retryable_exceptions=(RateLimitError,),
    )(func)
