"""Cache-first provider execution with domain-local failure containment."""

import hashlib
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from cache.repository import CacheRepository
from contracts.normalized_data import DataStatus, NormalizedData
from contracts.security import SecurityIdentity
from .base import ProviderContext, ProviderKind
from .registry import ProviderRegistry


class ProviderOrchestrator:
    def __init__(self, registry: Optional[ProviderRegistry] = None, cache: Optional[CacheRepository] = None):
        self.registry = registry or ProviderRegistry()
        self.cache = cache or CacheRepository()

    def fetch(self, kind: ProviderKind, security: Optional[SecurityIdentity], context: ProviderContext) -> NormalizedData:
        providers = self.registry.providers_for(kind)
        if not providers:
            return self._unavailable(kind, security, context, "provider_not_configured")
        provider = providers[0]
        key = self._cache_key(provider.name, kind, security, context)
        cached = self.cache.get(key)
        if cached:
            return cached
        if context.offline:
            stale = self.cache.get(key, allow_stale=True)
            return stale or self._fallback(kind, security, context, "offline_cache_miss")
        last_error = None
        for provider in providers:
            started = time.monotonic()
            try:
                value = provider.fetch(security, context)
                self._validate_as_of(value, context)
                if value.status in {DataStatus.REAL, DataStatus.CACHED}:
                    self.cache.put(key, provider.name, value, stale_seconds=provider.ttl_seconds)
                return value
            except Exception as exc:  # failure is confined to this data domain
                last_error = type(exc).__name__
                _ = started
        stale = self.cache.get(key, allow_stale=context.allow_stale)
        return stale or self._fallback(kind, security, context, last_error or "provider_error")

    @staticmethod
    def _cache_key(provider: str, kind: ProviderKind, security: Optional[SecurityIdentity], context: ProviderContext) -> str:
        security_id = security.security_id if security else "GLOBAL"
        bucket = context.as_of.date().isoformat()
        raw = f"{provider}:{kind.value}:{security_id}:{bucket}:v1"
        return hashlib.sha256(raw.encode()).hexdigest()

    @staticmethod
    def _validate_as_of(value: NormalizedData, context: ProviderContext) -> None:
        if value.observed_at and value.observed_at > context.as_of:
            raise ValueError("look_ahead_data_rejected")

    @staticmethod
    def _unavailable(kind, security, context, code):
        return NormalizedData(security.security_id if security else None, security.ticker if security else None,
            kind.value, {}, "unavailable", DataStatus.UNAVAILABLE, 0.0, None,
            datetime.now(timezone.utc), None, request_id=context.request_id, error_code=code)

    @staticmethod
    def _fallback(kind, security, context, code):
        return NormalizedData(security.security_id if security else None, security.ticker if security else None,
            kind.value, {}, "fallback", DataStatus.FALLBACK, 0.0, None,
            datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(minutes=5),
            is_fallback=True, request_id=context.request_id, error_code=code)
