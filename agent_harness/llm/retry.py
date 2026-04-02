"""Retry engine — exponential backoff with jitter and error classification.

Ported from Claude Code's withRetry.ts. Provides a reusable retry wrapper
for LLM API calls with configurable backoff, error classification, and
retry-after header support.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ErrorCategory(str, Enum):
    """Classification of API errors for retry decisions."""

    RATE_LIMIT = "rate_limit"           # 429 — too many requests
    OVERLOADED = "overloaded"           # 529 — server overloaded
    SERVER_ERROR = "server_error"       # 5xx — transient server issue
    TIMEOUT = "timeout"                 # 408 or connection timeout
    CONTEXT_OVERFLOW = "context_overflow"  # Prompt too long
    AUTH_ERROR = "auth_error"           # 401/403 — not retryable
    CLIENT_ERROR = "client_error"       # 400 (non-overflow) — not retryable
    CONNECTION_ERROR = "connection_error"  # Network errors
    UNKNOWN = "unknown"


@dataclass
class RetryConfig:
    """Configuration for the retry engine.

    Attributes:
        max_retries: Maximum number of retry attempts (default 5).
        base_delay_ms: Initial delay in milliseconds (default 500).
        max_delay_ms: Maximum delay cap in milliseconds (default 32000).
        jitter_fraction: Random jitter as fraction of base delay (default 0.25).
        retryable_status_codes: HTTP status codes that should be retried.
    """

    max_retries: int = 5
    base_delay_ms: int = 500
    max_delay_ms: int = 32_000
    jitter_fraction: float = 0.25
    retryable_status_codes: set[int] = field(
        default_factory=lambda: {408, 409, 429, 500, 502, 503, 504, 529}
    )


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, last_error: Exception, attempts: int):
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(
            f"Retry exhausted after {attempts} attempts. Last error: {last_error}"
        )


def get_retry_delay(
    attempt: int,
    config: RetryConfig,
    retry_after: float | None = None,
) -> float:
    """Calculate retry delay with exponential backoff and jitter.

    Args:
        attempt: Current attempt number (1-based).
        config: Retry configuration.
        retry_after: Optional server-suggested delay in seconds.

    Returns:
        Delay in seconds.
    """
    if retry_after is not None and retry_after > 0:
        return min(retry_after, config.max_delay_ms / 1000.0)

    # Exponential backoff: base * 2^(attempt-1)
    delay_ms = config.base_delay_ms * (2 ** (attempt - 1))
    delay_ms = min(delay_ms, config.max_delay_ms)

    # Add jitter: +0 to jitter_fraction of base_delay
    jitter_ms = random.uniform(0, config.base_delay_ms * config.jitter_fraction)
    delay_ms += jitter_ms

    return delay_ms / 1000.0


def classify_error(error: Exception) -> ErrorCategory:
    """Classify an exception into an ErrorCategory.

    Works with common patterns from anthropic and openai SDKs:
    - Checks for .status_code attribute (SDK APIError types)
    - Checks error message patterns for context overflow
    - Falls back to connection/timeout detection by exception type name
    """
    status_code = getattr(error, "status_code", None)

    if status_code is not None:
        if status_code == 429:
            return ErrorCategory.RATE_LIMIT
        if status_code == 529:
            return ErrorCategory.OVERLOADED
        if status_code in (401, 403):
            return ErrorCategory.AUTH_ERROR
        if status_code == 408:
            return ErrorCategory.TIMEOUT
        if status_code == 400:
            msg = str(error).lower()
            if "too long" in msg or "too many tokens" in msg or "context" in msg:
                return ErrorCategory.CONTEXT_OVERFLOW
            return ErrorCategory.CLIENT_ERROR
        if 500 <= status_code < 600:
            return ErrorCategory.SERVER_ERROR

    # Check by exception type name / message for SDK-agnostic detection
    error_type = type(error).__name__.lower()
    error_msg = str(error).lower()

    if "timeout" in error_type or "timeout" in error_msg or "timed out" in error_msg:
        return ErrorCategory.TIMEOUT
    if "connection" in error_type or "connect" in error_msg:
        return ErrorCategory.CONNECTION_ERROR
    if "overload" in error_msg:
        return ErrorCategory.OVERLOADED
    if "rate" in error_msg and "limit" in error_msg:
        return ErrorCategory.RATE_LIMIT

    return ErrorCategory.UNKNOWN


def should_retry(error: Exception, config: RetryConfig) -> bool:
    """Determine if an error should be retried.

    Non-retryable: AUTH_ERROR, CLIENT_ERROR
    Retryable: RATE_LIMIT, OVERLOADED, SERVER_ERROR, TIMEOUT, CONNECTION_ERROR
    CONTEXT_OVERFLOW: not retried (requires user action)
    UNKNOWN: retried (optimistic)
    """
    category = classify_error(error)

    if category in (ErrorCategory.AUTH_ERROR, ErrorCategory.CLIENT_ERROR,
                    ErrorCategory.CONTEXT_OVERFLOW):
        return False

    if category in (ErrorCategory.RATE_LIMIT, ErrorCategory.OVERLOADED,
                    ErrorCategory.SERVER_ERROR, ErrorCategory.TIMEOUT,
                    ErrorCategory.CONNECTION_ERROR):
        return True

    # UNKNOWN — retry optimistically
    return True


def _extract_retry_after(error: Exception) -> float | None:
    """Extract retry-after header value from an API error, if present."""
    # anthropic SDK: error.response.headers.get("retry-after")
    response = getattr(error, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None)
        if headers is not None:
            retry_after = None
            if hasattr(headers, "get"):
                retry_after = headers.get("retry-after")
            if retry_after is not None:
                try:
                    return float(retry_after)
                except (ValueError, TypeError):
                    pass

    # openai SDK: error.headers might be directly available
    headers = getattr(error, "headers", None)
    if headers is not None and hasattr(headers, "get"):
        retry_after = headers.get("retry-after")
        if retry_after is not None:
            try:
                return float(retry_after)
            except (ValueError, TypeError):
                pass

    return None


def parse_context_overflow(error: Exception) -> dict[str, int] | None:
    """Extract token counts from a context overflow error message.

    Returns dict with 'actual_tokens' and 'limit_tokens' if parseable.
    """
    msg = str(error)
    # Common patterns:
    # "prompt is too long: 150000 tokens > 128000"
    # "This request would exceed the context window of 200000 tokens"
    match = re.search(r"(\d[\d,]*)\s*tokens?\s*>\s*(\d[\d,]*)", msg)
    if match:
        actual = int(match.group(1).replace(",", ""))
        limit = int(match.group(2).replace(",", ""))
        return {"actual_tokens": actual, "limit_tokens": limit}

    return None


async def with_retry(
    operation: Callable[..., Awaitable[T]],
    config: RetryConfig | None = None,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> T:
    """Execute an async operation with retry logic.

    Args:
        operation: Async callable to execute. Called with no arguments.
        config: Retry configuration. Uses defaults if None.
        on_retry: Optional callback(attempt, error, delay_seconds) before each retry.

    Returns:
        The result of the operation.

    Raises:
        RetryExhaustedError: If all retries are exhausted.
        Exception: Non-retryable errors are raised immediately.
    """
    cfg = config or RetryConfig()

    last_error: Exception | None = None

    for attempt in range(1, cfg.max_retries + 2):  # +1 for initial attempt, +1 for range
        try:
            return await operation()
        except Exception as e:
            last_error = e

            if attempt > cfg.max_retries:
                break

            if not should_retry(e, cfg):
                raise

            retry_after = _extract_retry_after(e)
            delay = get_retry_delay(attempt, cfg, retry_after)

            category = classify_error(e)
            logger.warning(
                f"Retry {attempt}/{cfg.max_retries} after {delay:.1f}s "
                f"[{category.value}]: {e}"
            )

            if on_retry:
                on_retry(attempt, e, delay)

            await asyncio.sleep(delay)

    assert last_error is not None
    raise RetryExhaustedError(last_error, cfg.max_retries + 1)
