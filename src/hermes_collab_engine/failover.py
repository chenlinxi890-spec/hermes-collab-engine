"""Cascading provider failover — HealthMonitor, FailoverChain, FailoverAttempt.

Provides thread-safe health monitoring via HTTP HEAD probes and a
failover chain that skips unhealthy providers in a configured order.
Designed for Hermes Collab Engine's multi-provider worker dispatch,
but usable standalone.
"""
from __future__ import annotations

import dataclasses
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Callable


# ---------------------------------------------------------------------------
# FailoverAttempt — immutable record of one health-check or dispatch try
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class FailoverAttempt:
    """Immutable record of a single failover attempt.

    Attributes:
        provider_name: Human-readable provider label (e.g. ``"anthropic"``).
        success: Whether the probe or dispatch succeeded.
        error: Error message if *success* is ``False``; empty string otherwise.
        timestamp: Unix timestamp (``time.time()``) of the attempt.
    """
    provider_name: str
    success: bool
    error: str = ""
    timestamp: float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_name": self.provider_name,
            "success": self.success,
            "error": self.error,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# HealthMonitor — thread-safe HTTP HEAD probe for a single provider
# ---------------------------------------------------------------------------


class HealthMonitor:
    """Thread-safe health monitor that probes a provider endpoint via HTTP HEAD.

    Usage::

        monitor = HealthMonitor("https://api.anthropic.com")
        ok = monitor.check()           # True if HEAD 2xx
        print(monitor.fail_count)      # consecutive failures
        monitor.reset()                # reset fail_count to 0

    Thread-safety is guaranteed via an internal ``threading.Lock``.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 2.0,
        max_fail: int = 3,
        probe_path: str = "/health",
        probe_factory: Callable[..., Any] | None = None,
    ) -> None:
        """
        Args:
            base_url: Root URL of the provider API (e.g. ``"https://api.anthropic.com"``).
            timeout: HTTP request timeout in seconds.
            max_fail: Consecutive failure threshold after which the provider
                is considered unhealthy by :class:`FailoverChain`.
            probe_path: Path appended to *base_url* for the health HEAD request.
            probe_factory: Optional callable that returns a file-like or
                response object for testing. Defaults to ``urllib.request.urlopen``.
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_fail = max_fail
        self.probe_url = f"{self.base_url}{probe_path}"
        self._fail_count: int = 0
        self._lock = threading.Lock()
        self._probe_factory = probe_factory or urllib.request.urlopen
        self._last_exception: str = ""

    @property
    def fail_count(self) -> int:
        """Consecutive failure count (thread-safe)."""
        with self._lock:
            return self._fail_count

    @property
    def last_exception(self) -> str:
        """Last exception message from the most recent failed check."""
        with self._lock:
            return self._last_exception

    def check(self) -> bool:
        """Perform a single health check via HTTP HEAD.

        Returns:
            ``True`` if the endpoint responded with a 2xx status code,
            ``False`` otherwise.

        Thread-safe: internal mutations (``fail_count``, ``last_exception``)
        are protected by the instance lock.
        """
        try:
            req = urllib.request.Request(self.probe_url, method="HEAD")
            with self._probe_factory(req, timeout=self.timeout) as resp:
                ok = 200 <= resp.status < 300
        except (urllib.error.URLError, OSError, ValueError) as exc:
            with self._lock:
                self._fail_count += 1
                self._last_exception = str(exc)
            return False

        with self._lock:
            if ok:
                self._fail_count = 0
                self._last_exception = ""
            else:
                self._fail_count += 1
                self._last_exception = f"HTTP {resp.status}"
        return ok

    def reset(self) -> None:
        """Reset the fail count and last exception to zero/empty."""
        with self._lock:
            self._fail_count = 0
            self._last_exception = ""


# ---------------------------------------------------------------------------
# ProviderSlot — internal holder for one position in the failover chain
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _ProviderSlot:
    name: str
    base_url: str
    api_key: str
    default_model: str
    monitor: HealthMonitor
    enabled: bool = True


# ---------------------------------------------------------------------------
# FailoverChain — ordered round-robin across healthy providers
# ---------------------------------------------------------------------------


class FailoverChain:
    """Ordered failover chain that picks the next healthy provider.

    Providers are checked in definition order. A provider whose
    :class:`HealthMonitor` has exceeded ``max_fail`` consecutive failures
    is skipped until its monitor is explicitly reset or its health check
    succeeds again.

    Usage::

        chain = FailoverChain([
            {"name": "primary",   "base_url": "https://api.anthropic.com", ...},
            {"name": "secondary", "base_url": "https://api.deepseek.com", ...},
        ])
        provider = chain.next_healthy()
        if provider:
            print(f"Dispatch to {provider.name}")
        else:
            print("All providers unhealthy")
    """

    def __init__(
        self,
        providers: list[dict[str, Any]],
        *,
        timeout: float = 2.0,
        max_fail: int = 3,
        monitor_factory: Callable[..., HealthMonitor] | None = None,
    ) -> None:
        """
        Args:
            providers: Ordered list of provider config dicts. Each dict must
                contain at least ``"name"`` and ``"base_url"``.
            timeout: Default HTTP probe timeout for each provider's monitor.
            max_fail: Consecutive failure threshold for marking a provider
                unhealthy.
            monitor_factory: Optional factory for creating health monitors.
                Defaults to ``HealthMonitor``.
        """
        self._monitor_factory = monitor_factory or HealthMonitor
        self._slots: list[_ProviderSlot] = []
        self._lock = threading.Lock()
        self._cursor = 0
        self._attempts: list[FailoverAttempt] = []

        for cfg in providers:
            monitor = self._monitor_factory(
                cfg.get("base_url", ""),
                timeout=cfg.get("timeout", timeout),
                max_fail=cfg.get("max_fail", max_fail),
            )
            slot = _ProviderSlot(
                name=cfg["name"],
                base_url=cfg.get("base_url", ""),
                api_key=cfg.get("api_key", ""),
                default_model=cfg.get("default_model", ""),
                monitor=monitor,
                enabled=cfg.get("enabled", True),
            )
            self._slots.append(slot)

    @property
    def slots(self) -> list[dict[str, Any]]:
        """Snapshot of all provider slots (read-only)."""
        with self._lock:
            return [
                {
                    "name": s.name,
                    "base_url": s.base_url,
                    "default_model": s.default_model,
                    "enabled": s.enabled,
                    "healthy": s.monitor.fail_count < s.monitor.max_fail,
                    "fail_count": s.monitor.fail_count,
                }
                for s in self._slots
            ]

    @property
    def attempts(self) -> list[FailoverAttempt]:
        """List of all failover attempts made so far."""
        with self._lock:
            return list(self._attempts)

    def next_healthy(self) -> _ProviderSlot | None:
        """Return the next healthy provider slot, or ``None`` if all are down.

        Iterates over the chain starting from the last cursor position.
        A provider is healthy if:
        - its ``enabled`` flag is ``True``, and
        - its monitor's ``fail_count`` < ``max_fail``.

        The cursor advances after each call for basic round-robin across
        consecutive healthy providers.
        """
        with self._lock:
            n = len(self._slots)
            for _ in range(n):
                slot = self._slots[self._cursor]
                self._cursor = (self._cursor + 1) % n
                if not slot.enabled:
                    continue
                if slot.monitor.fail_count < slot.monitor.max_fail:
                    return slot
            return None

    def check_all(self) -> list[FailoverAttempt]:
        """Probe every enabled provider once and update internal state.

        Returns a list of :class:`FailoverAttempt` records reflecting each
        probe result.
        """
        results: list[FailoverAttempt] = []
        for slot in self._slots:
            if not slot.enabled:
                continue
            ok = slot.monitor.check()
            attempt = FailoverAttempt(
                provider_name=slot.name,
                success=ok,
                error="" if ok else f"fail_count={slot.monitor.fail_count}/{slot.monitor.max_fail}",
            )
            results.append(attempt)
        with self._lock:
            self._attempts.extend(results)
        return results

    def attempt(self) -> FailoverAttempt:
        """Attempt to dispatch via the next healthy provider.

        This is a convenience method that calls :meth:`next_healthy` and
        records the result as a :class:`FailoverAttempt`.

        Returns:
            A ``FailoverAttempt`` with ``success=True`` if a healthy provider
            was found, ``success=False`` with an error message otherwise.
        """
        slot = self.next_healthy()
        if slot is None:
            attempt = FailoverAttempt(
                provider_name="(none)",
                success=False,
                error="all providers unhealthy or disabled",
            )
        else:
            attempt = FailoverAttempt(
                provider_name=slot.name,
                success=True,
            )
        with self._lock:
            self._attempts.append(attempt)
        return attempt

    def reset_all(self) -> None:
        """Reset health state for all providers (clear fail counts)."""
        for slot in self._slots:
            slot.monitor.reset()


__all__ = [
    "FailoverAttempt",
    "HealthMonitor",
    "FailoverChain",
]
