from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Callable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetrySettings:
    attempts: int = 1
    initial_delay_seconds: float = 0.25
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 2.0

    @classmethod
    def from_env(cls) -> "RetrySettings":
        attempts = max(1, int((os.getenv("PREPROCESS_RETRY_ATTEMPTS", "1") or "1").strip()))
        initial_delay = max(0.0, float((os.getenv("PREPROCESS_RETRY_INITIAL_DELAY", "0.25") or "0.25").strip()))
        backoff = max(1.0, float((os.getenv("PREPROCESS_RETRY_BACKOFF", "2.0") or "2.0").strip()))
        max_delay = max(initial_delay, float((os.getenv("PREPROCESS_RETRY_MAX_DELAY", "2.0") or "2.0").strip()))
        return cls(
            attempts=attempts,
            initial_delay_seconds=initial_delay,
            backoff_multiplier=backoff,
            max_delay_seconds=max_delay,
        )


def run_with_retry(
    operation: Callable[[], T],
    *,
    settings: RetrySettings | None = None,
    retry_if: Callable[[Exception], bool] | None = None,
    on_retry: Callable[[int, Exception, float], None] | None = None,
) -> T:
    retry_settings = settings or RetrySettings.from_env()
    attempt = 1
    delay = retry_settings.initial_delay_seconds

    while True:
        try:
            return operation()
        except Exception as exc:
            should_retry = retry_if(exc) if retry_if is not None else False
            if attempt >= retry_settings.attempts or not should_retry:
                raise
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            if delay > 0:
                time.sleep(delay)
            delay = min(delay * retry_settings.backoff_multiplier, retry_settings.max_delay_seconds)
            attempt += 1
