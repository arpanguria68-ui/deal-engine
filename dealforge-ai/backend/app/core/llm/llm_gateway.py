"""
LLM Gateway — Central token budget, rate-limit, retry, and cost control layer.

All LLM calls should funnel through this gateway so we can enforce:
1. Rolling-window rate limits (RPM/TPM) per vendor
2. Exponential backoff + jitter on 429/5xx
3. Automatic fallback (cloud → cloud → local)
4. Hybrid compression (local summarize → cloud reason)
5. Daily budget guardrails
6. Response caching for deterministic (temperature=0) calls
"""

import time
import random
import hashlib
import json
import asyncio
from collections import deque
from typing import Dict, Any, Optional, List, Tuple, Callable
from dataclasses import dataclass, field
import structlog

from app.config import get_settings

logger = structlog.get_logger()


# ═══════════════════════════════════════════════════════════
#  1. UsageWindow — Track requests/tokens in a rolling window
# ═══════════════════════════════════════════════════════════


class UsageWindow:
    """Sliding window counter for rate tracking."""

    def __init__(self, window_seconds: int):
        self.window: deque = deque()
        self.window_seconds = window_seconds

    def add(self, amount: int = 1):
        now = time.time()
        self.window.append((now, amount))
        self._prune(now)

    def total(self) -> int:
        now = time.time()
        self._prune(now)
        return sum(v for _, v in self.window)

    def _prune(self, now: float):
        cutoff = now - self.window_seconds
        while self.window and self.window[0][0] < cutoff:
            self.window.popleft()


# ═══════════════════════════════════════════════════════════
#  2. VendorLimiter — Per-provider rate + token limits
# ═══════════════════════════════════════════════════════════


@dataclass
class VendorLimits:
    """Rate limit thresholds for a vendor (set to ~85% of actual quota)."""

    max_rpm: int = 50  # Requests per minute
    max_tpm: int = 100_000  # Tokens per minute
    max_rpd: int = 10_000  # Requests per day
    max_tokens_month: int = 0  # 0 = unlimited


class VendorLimiter:
    """Enforce soft rate limits per vendor."""

    def __init__(self, name: str, limits: VendorLimits):
        self.name = name
        self.limits = limits
        self.req_minute = UsageWindow(60)
        self.tok_minute = UsageWindow(60)
        self.req_day = UsageWindow(86400)
        self.tok_month = UsageWindow(30 * 86400)
        self.total_cost_usd = 0.0

    def can_send(self, est_tokens: int = 500) -> bool:
        """Check if we're within soft limits."""
        if self.req_minute.total() + 1 > self.limits.max_rpm:
            logger.warning(
                "rate_limit_rpm",
                vendor=self.name,
                current=self.req_minute.total(),
                limit=self.limits.max_rpm,
            )
            return False
        if self.tok_minute.total() + est_tokens > self.limits.max_tpm:
            logger.warning(
                "rate_limit_tpm",
                vendor=self.name,
                current=self.tok_minute.total(),
                limit=self.limits.max_tpm,
            )
            return False
        if self.limits.max_rpd > 0 and self.req_day.total() + 1 > self.limits.max_rpd:
            logger.warning(
                "rate_limit_rpd",
                vendor=self.name,
                current=self.req_day.total(),
                limit=self.limits.max_rpd,
            )
            return False
        return True

    def register(self, tokens_used: int):
        """Record a completed call."""
        self.req_minute.add(1)
        self.tok_minute.add(tokens_used)
        self.req_day.add(1)
        self.tok_month.add(tokens_used)

    def get_usage(self) -> Dict[str, Any]:
        return {
            "vendor": self.name,
            "rpm": {"current": self.req_minute.total(), "limit": self.limits.max_rpm},
            "tpm": {"current": self.tok_minute.total(), "limit": self.limits.max_tpm},
            "rpd": {"current": self.req_day.total(), "limit": self.limits.max_rpd},
            "monthly_tokens": self.tok_month.total(),
        }


# ═══════════════════════════════════════════════════════════
#  3. Retry with Exponential Backoff + Jitter
# ═══════════════════════════════════════════════════════════

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


async def exponential_backoff_retry(
    fn: Callable,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Any:
    """Retry async function with capped exponential backoff + jitter."""
    attempt = 0
    while True:
        try:
            return await fn()
        except Exception as e:
            status = getattr(e, "status_code", None) or getattr(e, "status", None)
            # Also check for httpx.HTTPStatusError
            if hasattr(e, "response"):
                status = getattr(e.response, "status_code", status)

            if status not in RETRYABLE_STATUS or attempt >= max_retries:
                raise

            sleep = min(max_delay, base_delay * (2**attempt))
            sleep = sleep * (0.8 + 0.4 * random.random())  # ±20% jitter
            logger.warning(
                "llm_retry",
                attempt=attempt + 1,
                status=status,
                backoff_s=f"{sleep:.1f}",
                error=str(e)[:100],
            )
            await asyncio.sleep(sleep)
            attempt += 1


# ═══════════════════════════════════════════════════════════
#  4. Response Cache (temperature=0 deterministic calls)
# ═══════════════════════════════════════════════════════════


class ResponseCache:
    """Simple in-memory LRU cache for deterministic LLM responses."""

    def __init__(self, max_size: int = 500):
        self._cache: Dict[str, Tuple[str, float]] = {}
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(provider: str, messages: List[Dict], model: str) -> str:
        raw = json.dumps({"p": provider, "m": messages, "model": model}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, provider: str, messages: List[Dict], model: str) -> Optional[str]:
        key = self._key(provider, messages, model)
        if key in self._cache:
            self.hits += 1
            return self._cache[key][0]
        self.misses += 1
        return None

    def set(self, provider: str, messages: List[Dict], model: str, response: str):
        key = self._key(provider, messages, model)
        if len(self._cache) >= self.max_size:
            # Evict oldest
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[key] = (response, time.time())


# ═══════════════════════════════════════════════════════════
#  5. Token Counter (rough estimation)
# ═══════════════════════════════════════════════════════════


class TokenCounter:
    """Rough token estimation (~4 chars per token for English)."""

    @staticmethod
    def estimate(text: str) -> int:
        return max(1, len(text) // 4)

    @staticmethod
    def estimate_messages(messages: List[Dict]) -> int:
        total = 0
        for m in messages:
            total += TokenCounter.estimate(m.get("content", ""))
            total += 4  # overhead per message
        return total


# ═══════════════════════════════════════════════════════════
#  6. LLM Gateway — Central orchestration point
# ═══════════════════════════════════════════════════════════

# Default vendor limits (~85% of typical free/low-tier quotas)
DEFAULT_VENDOR_LIMITS = {
    "gemini": VendorLimits(max_rpm=12, max_tpm=80_000, max_rpd=1_400),
    "openai": VendorLimits(max_rpm=50, max_tpm=150_000, max_rpd=8_000),
    "mistral": VendorLimits(max_rpm=5, max_tpm=400_000, max_rpd=4_000),
    "ollama": VendorLimits(max_rpm=999, max_tpm=999_999, max_rpd=999_999),
    "lmstudio": VendorLimits(max_rpm=999, max_tpm=999_999, max_rpd=999_999),
}

# Fallback chain: if primary is over-quota, try these in order
FALLBACK_CHAIN = {
    "gemini": ["mistral", "openai", "ollama"],
    "openai": ["gemini", "mistral", "ollama"],
    "mistral": ["gemini", "openai", "ollama"],
    "ollama": ["lmstudio", "gemini", "mistral"],
    "lmstudio": ["ollama", "gemini", "mistral"],
}


class LLMGateway:
    """
    Central gateway that all code uses instead of calling Gemini/Mistral/Ollama directly.

    Features:
    - Token + request budgeting per vendor
    - Automatic fallback when quota is tight
    - Exponential backoff retry on 429/5xx
    - Response caching for deterministic calls
    - Hybrid compression (local summarize → cloud reason)
    - Usage analytics
    """

    def __init__(self):
        self.limiters: Dict[str, VendorLimiter] = {}
        self.cache = ResponseCache()
        self.counter = TokenCounter()
        self._call_log: deque = deque(maxlen=1000)

        # Initialize limiters for all vendors
        for vendor, limits in DEFAULT_VENDOR_LIMITS.items():
            self.limiters[vendor] = VendorLimiter(vendor, limits)

        logger.info("LLMGateway initialized", vendors=list(self.limiters.keys()))

    def update_vendor_limits(self, vendor: str, limits: VendorLimits):
        """Update rate limits for a vendor (e.g., when user changes tier)."""
        self.limiters[vendor] = VendorLimiter(vendor, limits)
        logger.info(
            "vendor_limits_updated",
            vendor=vendor,
            rpm=limits.max_rpm,
            tpm=limits.max_tpm,
        )

    async def call(
        self,
        provider: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Central LLM call — all requests go through here.

        Returns: {"content": str, "provider_used": str, "tokens_est": int,
                  "cached": bool, "fallback_used": bool, ...}
        """
        from app.core.llm import get_llm_client

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        est_in = self.counter.estimate_messages(messages)
        est_total = est_in + max_tokens

        # ── Cache check (only for temperature=0) ──
        if use_cache and temperature == 0:
            settings = get_settings()
            model = self._get_model_name(provider, settings)
            cached = self.cache.get(provider, messages, model)
            if cached:
                logger.info("llm_cache_hit", provider=provider)
                return {
                    "content": cached,
                    "provider_used": provider,
                    "tokens_est": est_total,
                    "cached": True,
                    "fallback_used": False,
                }

        # ── Rate limit check + fallback chain ──
        actual_provider = provider
        fallback_used = False

        limiter = self.limiters.get(provider)
        if limiter and not limiter.can_send(est_total):
            # Try fallback chain
            actual_provider, fallback_used = self._find_available_provider(
                provider, est_total
            )
            if actual_provider is None:
                return {
                    "content": "[Rate limited] All providers over quota. Try again later.",
                    "provider_used": "none",
                    "tokens_est": est_total,
                    "cached": False,
                    "fallback_used": True,
                    "error": "all_providers_over_quota",
                }

        # ── Execute with retry ──
        client = get_llm_client(actual_provider)

        async def do_call():
            return await client.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                tools=tools,
            )

        try:
            result = await exponential_backoff_retry(do_call)
        except Exception as e:
            logger.error("llm_call_failed", provider=actual_provider, error=str(e))
            # Last resort: try local
            if actual_provider not in ("ollama", "lmstudio"):
                try:
                    client = get_llm_client("ollama")
                    result = await client.generate(
                        prompt=prompt, system_prompt=system_prompt
                    )
                    actual_provider = "ollama"
                    fallback_used = True
                except Exception:
                    return {
                        "content": f"[Error] LLM call failed: {str(e)[:200]}",
                        "provider_used": actual_provider,
                        "tokens_est": est_total,
                        "cached": False,
                        "fallback_used": fallback_used,
                        "error": str(e),
                    }

        content = result.get("content", "")
        actual_tokens = self.counter.estimate(content) + est_in

        # Register usage
        if actual_provider in self.limiters:
            self.limiters[actual_provider].register(actual_tokens)

        # Cache deterministic responses
        if use_cache and temperature == 0 and content:
            settings = get_settings()
            model = self._get_model_name(actual_provider, settings)
            self.cache.set(actual_provider, messages, model, content)

        # Log call
        self._call_log.append(
            {
                "provider": actual_provider,
                "tokens": actual_tokens,
                "fallback": fallback_used,
                "cached": False,
                "time": time.time(),
            }
        )

        return {
            **result,
            "provider_used": actual_provider,
            "tokens_est": actual_tokens,
            "cached": False,
            "fallback_used": fallback_used,
        }

    async def hybrid_reasoning(
        self,
        question: str,
        context: str,
        cloud_provider: str = None,
        max_context_tokens: int = 4000,
    ) -> Dict[str, Any]:
        """
        Hybrid pattern: compress with local LLM, then reason with cloud.
        Saves cloud TPM by sending summarized context instead of full docs.
        """
        if cloud_provider is None:
            settings = get_settings()
            cloud_provider = getattr(settings, "DEFAULT_LLM_PROVIDER", "gemini")

        context_tokens = self.counter.estimate(context)

        if context_tokens > max_context_tokens:
            # Step 1: Local compression
            logger.info(
                "hybrid_compress",
                original_tokens=context_tokens,
                threshold=max_context_tokens,
            )
            compress_result = await self.call(
                provider="ollama",
                prompt=f"Summarize the following context for a financial analyst to answer "
                f"this question: {question}\n\nContext:\n{context}",
                system_prompt="You are a concise financial summarizer. "
                "Extract only key facts, numbers, and relevant details. "
                "Output a bullet-point summary under 500 words.",
                max_tokens=2048,
                temperature=0.1,
            )
            context = compress_result.get("content", context[: max_context_tokens * 4])

        # Step 2: Cloud reasoning
        return await self.call(
            provider=cloud_provider,
            prompt=f"Question: {question}\n\nContext:\n{context}",
            system_prompt="You are a senior investment analyst at a top-tier firm.",
            max_tokens=2048,
            temperature=0.2,
        )

    def _find_available_provider(
        self, original: str, est_tokens: int
    ) -> Tuple[Optional[str], bool]:
        """Walk the fallback chain to find a provider with quota."""
        chain = FALLBACK_CHAIN.get(original, ["ollama"])
        for alt in chain:
            limiter = self.limiters.get(alt)
            if limiter is None or limiter.can_send(est_tokens):
                logger.info("fallback_provider", original=original, fallback=alt)
                return alt, True
        return None, True

    @staticmethod
    def _get_model_name(provider: str, settings) -> str:
        model_map = {
            "gemini": "GEMINI_MODEL",
            "openai": "OPENAI_MODEL",
            "mistral": "MISTRAL_MODEL",
            "ollama": "OLLAMA_MODEL",
            "lmstudio": "LMSTUDIO_MODEL",
        }
        attr = model_map.get(provider, "GEMINI_MODEL")
        return getattr(settings, attr, "unknown")

    def get_usage_stats(self) -> Dict[str, Any]:
        """Return usage stats for all vendors + cache stats."""
        return {
            "vendors": {
                name: limiter.get_usage() for name, limiter in self.limiters.items()
            },
            "cache": {
                "hits": self.cache.hits,
                "misses": self.cache.misses,
                "size": len(self.cache._cache),
                "hit_rate": (
                    f"{self.cache.hits / max(1, self.cache.hits + self.cache.misses) * 100:.1f}%"
                ),
            },
            "recent_calls": len(self._call_log),
        }


# ═══════════════════════════════════════════════════════════
#  7. Singleton accessor
# ═══════════════════════════════════════════════════════════

_llm_gateway: Optional[LLMGateway] = None


def get_llm_gateway() -> LLMGateway:
    """Get or create the LLM gateway singleton."""
    global _llm_gateway
    if _llm_gateway is None:
        _llm_gateway = LLMGateway()
    return _llm_gateway
