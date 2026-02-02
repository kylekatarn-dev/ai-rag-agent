"""
Rate Limiting Module.

Provides per-user and global rate limiting for API calls.
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
import threading

from app.utils import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    requests_per_minute: int = 20
    requests_per_hour: int = 200
    tokens_per_minute: int = 40000
    tokens_per_hour: int = 400000
    burst_allowance: float = 1.5  # Allow 50% burst


@dataclass
class UserUsage:
    """Track usage for a single user."""
    minute_requests: list = field(default_factory=list)
    hour_requests: list = field(default_factory=list)
    minute_tokens: int = 0
    hour_tokens: int = 0
    last_minute_reset: float = field(default_factory=time.time)
    last_hour_reset: float = field(default_factory=time.time)


class RateLimiter:
    """
    Rate limiter for API calls.

    Features:
    - Per-user rate limiting
    - Global rate limiting
    - Token-based limiting (for LLM calls)
    - Sliding window algorithm
    - Burst allowance
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        """
        Initialize rate limiter.

        Args:
            config: Rate limit configuration
        """
        self.config = config or RateLimitConfig()
        self._users: dict[str, UserUsage] = defaultdict(UserUsage)
        self._global = UserUsage()
        self._lock = threading.Lock()

        logger.info(
            f"Rate limiter initialized: "
            f"{self.config.requests_per_minute}/min, "
            f"{self.config.requests_per_hour}/hour"
        )

    def check_limit(
        self,
        user_id: str = "global",
        tokens: int = 0,
    ) -> tuple[bool, Optional[str], Optional[int]]:
        """
        Check if request is within rate limits.

        Args:
            user_id: User identifier (or "global" for global limit)
            tokens: Estimated tokens for this request

        Returns:
            Tuple of (allowed, reason, retry_after_seconds)
        """
        with self._lock:
            now = time.time()

            # Get user usage
            usage = self._users[user_id]

            # Clean up old requests
            self._cleanup_old_requests(usage, now)
            self._cleanup_old_requests(self._global, now)

            # Check minute limit
            minute_count = len(usage.minute_requests)
            minute_limit = int(self.config.requests_per_minute * self.config.burst_allowance)

            if minute_count >= minute_limit:
                retry_after = 60 - (now - usage.last_minute_reset)
                logger.warning(f"Rate limit exceeded for {user_id}: {minute_count}/{minute_limit} per minute")
                return False, "Prekrocen limit pozadavku za minutu", int(retry_after)

            # Check hour limit
            hour_count = len(usage.hour_requests)
            hour_limit = int(self.config.requests_per_hour * self.config.burst_allowance)

            if hour_count >= hour_limit:
                retry_after = 3600 - (now - usage.last_hour_reset)
                logger.warning(f"Rate limit exceeded for {user_id}: {hour_count}/{hour_limit} per hour")
                return False, "Prekrocen limit pozadavku za hodinu", int(retry_after)

            # Check token limits
            if tokens > 0:
                if usage.minute_tokens + tokens > self.config.tokens_per_minute:
                    retry_after = 60 - (now - usage.last_minute_reset)
                    return False, "Prekrocen limit tokenu za minutu", int(retry_after)

                if usage.hour_tokens + tokens > self.config.tokens_per_hour:
                    retry_after = 3600 - (now - usage.last_hour_reset)
                    return False, "Prekrocen limit tokenu za hodinu", int(retry_after)

            # Check global limits
            global_minute = len(self._global.minute_requests)
            global_limit = minute_limit * 10  # 10x user limit for global

            if global_minute >= global_limit:
                retry_after = 60 - (now - self._global.last_minute_reset)
                logger.warning(f"Global rate limit exceeded: {global_minute}/{global_limit}")
                return False, "Server je pretizen, zkuste pozdeji", int(retry_after)

            return True, None, None

    def record_request(
        self,
        user_id: str = "global",
        tokens: int = 0,
    ) -> None:
        """
        Record a request for rate limiting.

        Args:
            user_id: User identifier
            tokens: Tokens used in this request
        """
        with self._lock:
            now = time.time()
            usage = self._users[user_id]

            usage.minute_requests.append(now)
            usage.hour_requests.append(now)
            usage.minute_tokens += tokens
            usage.hour_tokens += tokens

            # Global tracking
            self._global.minute_requests.append(now)
            self._global.hour_requests.append(now)
            self._global.minute_tokens += tokens
            self._global.hour_tokens += tokens

    def _cleanup_old_requests(self, usage: UserUsage, now: float) -> None:
        """Remove expired requests from tracking."""
        minute_ago = now - 60
        hour_ago = now - 3600

        # Reset minute counters
        if now - usage.last_minute_reset >= 60:
            usage.minute_requests = [t for t in usage.minute_requests if t > minute_ago]
            usage.minute_tokens = 0
            usage.last_minute_reset = now

        # Reset hour counters
        if now - usage.last_hour_reset >= 3600:
            usage.hour_requests = [t for t in usage.hour_requests if t > hour_ago]
            usage.hour_tokens = 0
            usage.last_hour_reset = now

    def get_usage(self, user_id: str = "global") -> dict:
        """
        Get current usage stats for a user.

        Args:
            user_id: User identifier

        Returns:
            Dict with usage statistics
        """
        with self._lock:
            now = time.time()
            usage = self._users[user_id]
            self._cleanup_old_requests(usage, now)

            return {
                "requests_per_minute": len(usage.minute_requests),
                "requests_per_hour": len(usage.hour_requests),
                "tokens_per_minute": usage.minute_tokens,
                "tokens_per_hour": usage.hour_tokens,
                "limits": {
                    "requests_per_minute": self.config.requests_per_minute,
                    "requests_per_hour": self.config.requests_per_hour,
                    "tokens_per_minute": self.config.tokens_per_minute,
                    "tokens_per_hour": self.config.tokens_per_hour,
                },
            }

    def reset_user(self, user_id: str) -> None:
        """Reset usage for a specific user."""
        with self._lock:
            if user_id in self._users:
                del self._users[user_id]
                logger.debug(f"Reset rate limits for user: {user_id}")


# Singleton instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get singleton rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def check_rate_limit(user_id: str = "global", tokens: int = 0) -> tuple[bool, Optional[str]]:
    """
    Convenience function to check rate limit.

    Returns:
        Tuple of (allowed, error_message)
    """
    limiter = get_rate_limiter()
    allowed, reason, retry_after = limiter.check_limit(user_id, tokens)

    if not allowed and retry_after:
        return False, f"{reason}. Zkuste znovu za {retry_after} sekund."

    return allowed, reason


def record_api_call(user_id: str = "global", tokens: int = 0) -> None:
    """Convenience function to record an API call."""
    get_rate_limiter().record_request(user_id, tokens)
