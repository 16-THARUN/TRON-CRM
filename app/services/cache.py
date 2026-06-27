"""
app/services/cache.py
=====================
Lightweight in-process TTL cache using a plain dict.

Caching strategy
────────────────
  Layer       What is cached               TTL
  ─────────   ──────────────────────────   ─────
  dashboard   KPI aggregate totals          60 s
  chart_data  Pipeline stage counts         30 s
  (future)    Redis for multi-worker deploy  —

Why not Redis here?
  Single-worker uvicorn dev setup doesn't need Redis.
  To scale: replace cache_get/cache_set with aioredis calls —
  the call sites in main.py don't change at all.

Thread-safety note:
  asyncio is single-threaded; no lock needed for this dict.
"""

import time
from typing import Any, Optional

_store: dict[str, dict] = {}   # { key: {"value": ..., "expires_at": float} }


async def cache_get(key: str) -> Optional[Any]:
    """Return cached value if present and not expired, else None."""
    entry = _store.get(key)
    if entry and time.monotonic() < entry["expires_at"]:
        return entry["value"]
    _store.pop(key, None)   # evict expired entry
    return None


async def cache_set(key: str, value: Any, ttl: int = 60) -> None:
    """Store value with a TTL (seconds)."""
    _store[key] = {"value": value, "expires_at": time.monotonic() + ttl}


async def cache_invalidate(key: str) -> None:
    """Remove a key immediately (e.g. after a write operation)."""
    _store.pop(key, None)


async def cache_flush() -> None:
    """Flush entire cache (used in tests)."""
    _store.clear()
