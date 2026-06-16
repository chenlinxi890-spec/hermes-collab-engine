"""Tests for failover — HealthMonitor, FailoverChain, FailoverAttempt."""
from __future__ import annotations

import dataclasses
import io
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock

from src.hermes_collab_engine.failover import (
    FailoverAttempt,
    HealthMonitor,
    FailoverChain,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_response(req, timeout=1.0):
    """Probe factory that returns a 200 OK response."""
    return io.BytesIO(b"")


_ok_response.status = 200


class _FakeHTTPResponse(io.BytesIO):
    """Minimal fake response with .status attribute."""
    def __init__(self, status: int, data: bytes = b""):
        super().__init__(data)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _factory_for_status(status: int):
    """Return a probe factory that always returns *status*."""
    def factory(req, timeout=1.0):
        return _FakeHTTPResponse(status)
    return factory


def _raising_factory(error: Exception):
    """Return a probe factory that always raises *error*."""
    def factory(req, timeout=1.0):
        raise error
    return factory


# ---------------------------------------------------------------------------
# FailoverAttempt
# ---------------------------------------------------------------------------


class FailoverAttemptTests(unittest.TestCase):
    def test_default_timestamp(self):
        t1 = time.time()
        attempt = FailoverAttempt(provider_name="test", success=True)
        t2 = time.time()
        self.assertEqual(attempt.provider_name, "test")
        self.assertTrue(attempt.success)
        self.assertEqual(attempt.error, "")
        self.assertGreaterEqual(attempt.timestamp, t1)
        self.assertLessEqual(attempt.timestamp, t2)

    def test_with_error(self):
        attempt = FailoverAttempt(provider_name="p1", success=False, error="timeout")
        self.assertFalse(attempt.success)
        self.assertEqual(attempt.error, "timeout")

    def test_to_dict(self):
        attempt = FailoverAttempt(provider_name="p1", success=True, error="", timestamp=1000.0)
        d = attempt.to_dict()
        self.assertEqual(d["provider_name"], "p1")
        self.assertEqual(d["success"], True)
        self.assertEqual(d["timestamp"], 1000.0)

    def test_frozen(self):
        attempt = FailoverAttempt(provider_name="p1", success=True)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            attempt.provider_name = "p2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HealthMonitor
# ---------------------------------------------------------------------------


class HealthMonitorTests(unittest.TestCase):
    def test_construction(self):
        m = HealthMonitor("https://api.example.com", timeout=1.0, max_fail=3)
        self.assertEqual(m.base_url, "https://api.example.com")
        self.assertEqual(m.timeout, 1.0)
        self.assertEqual(m.max_fail, 3)
        self.assertEqual(m.probe_url, "https://api.example.com/health")
        self.assertEqual(m.fail_count, 0)
        self.assertEqual(m.last_exception, "")

    def test_check_success_resets_fail_count(self):
        m = HealthMonitor("https://api.example.com", probe_factory=_factory_for_status(200))
        self.assertTrue(m.check())
        self.assertEqual(m.fail_count, 0)

    def test_check_http_error_increments_fail_count(self):
        m = HealthMonitor("https://api.example.com", probe_factory=_factory_for_status(503))
        self.assertFalse(m.check())
        self.assertEqual(m.fail_count, 1)
        self.assertIn("HTTP 503", m.last_exception)

    def test_check_connection_error_increments(self):
        m = HealthMonitor(
            "https://api.example.com",
            probe_factory=_raising_factory(urllib.error.URLError("conn refused")),
        )
        self.assertFalse(m.check())
        self.assertEqual(m.fail_count, 1)
        self.assertIn("conn refused", m.last_exception)

    def test_check_oserror_increments(self):
        m = HealthMonitor(
            "https://api.example.com",
            probe_factory=_raising_factory(OSError("connection reset")),
        )
        self.assertFalse(m.check())
        self.assertEqual(m.fail_count, 1)

    def test_consecutive_failures_accumulate(self):
        m = HealthMonitor(
            "https://api.example.com",
            probe_factory=_raising_factory(urllib.error.URLError("down")),
        )
        for _ in range(5):
            m.check()
        self.assertEqual(m.fail_count, 5)

    def test_reset(self):
        m = HealthMonitor(
            "https://api.example.com",
            probe_factory=_raising_factory(urllib.error.URLError("down")),
        )
        m.check()
        self.assertEqual(m.fail_count, 1)
        m.reset()
        self.assertEqual(m.fail_count, 0)
        self.assertEqual(m.last_exception, "")

    def test_thread_safety(self):
        """Run concurrent checks; must not corrupt internal state."""
        m = HealthMonitor(
            "https://api.example.com",
            probe_factory=_raising_factory(urllib.error.URLError("err")),
        )
        errors: list[Exception] = []
        def worker():
            try:
                for _ in range(20):
                    m.check()
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(errors, [])
        self.assertEqual(m.fail_count, 8 * 20)

    def test_trailing_slash_on_base_url(self):
        m = HealthMonitor("https://api.example.com/", timeout=1.0)
        self.assertEqual(m.probe_url, "https://api.example.com/health")

    def test_http_201_is_success(self):
        m = HealthMonitor("https://api.example.com", probe_factory=_factory_for_status(201))
        self.assertTrue(m.check())

    def test_http_300_is_not_success(self):
        m = HealthMonitor("https://api.example.com", probe_factory=_factory_for_status(300))
        self.assertFalse(m.check())

    def test_http_404_is_failure(self):
        m = HealthMonitor("https://api.example.com", probe_factory=_factory_for_status(404))
        self.assertFalse(m.check())


# ---------------------------------------------------------------------------
# FailoverChain
# ---------------------------------------------------------------------------


class FailoverChainTests(unittest.TestCase):
    def test_empty_chain_returns_none(self):
        chain = FailoverChain([])
        self.assertIsNone(chain.next_healthy())

    def test_single_healthy_provider(self):
        chain = FailoverChain([
            {"name": "primary", "base_url": "https://api.primary.com"},
        ])
        slot = chain.next_healthy()
        self.assertIsNotNone(slot)
        self.assertEqual(slot.name, "primary")  # type: ignore[union-attr]

    def test_single_unhealthy_provider_skipped(self):
        chain = FailoverChain([
            {"name": "primary", "base_url": "https://api.primary.com", "max_fail": 2},
        ])
        # Exhaust fail count
        chain.slots[0]["fail_count"]  # init
        for slot in chain._slots:
            slot.monitor._fail_count = 2  # Trigger unhealthy
        self.assertIsNone(chain.next_healthy())

    def test_fallback_to_secondary(self):
        chain = FailoverChain([
            {"name": "primary", "base_url": "https://api.primary.com", "max_fail": 1},
            {"name": "secondary", "base_url": "https://api.secondary.com", "max_fail": 3},
        ])
        # Make primary unhealthy
        primary_slot = chain._slots[0]
        primary_slot.monitor._fail_count = 1
        self.assertEqual(primary_slot.monitor.fail_count, 1)

        slot = chain.next_healthy()
        self.assertIsNotNone(slot)
        self.assertEqual(slot.name, "secondary")  # type: ignore[union-attr]

    def test_all_unhealthy_returns_none(self):
        chain = FailoverChain([
            {"name": "p1", "base_url": "https://a.com", "max_fail": 1},
            {"name": "p2", "base_url": "https://b.com", "max_fail": 1},
        ])
        for slot in chain._slots:
            slot.monitor._fail_count = 1
        self.assertIsNone(chain.next_healthy())

    def test_disabled_provider_skipped(self):
        chain = FailoverChain([
            {"name": "disabled", "base_url": "https://a.com", "enabled": False},
            {"name": "enabled", "base_url": "https://b.com", "enabled": True},
        ])
        slot = chain.next_healthy()
        self.assertEqual(slot.name, "enabled")  # type: ignore[union-attr]

    def test_slots_property(self):
        chain = FailoverChain([
            {"name": "p1", "base_url": "https://a.com"},
        ])
        slots = chain.slots
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0]["name"], "p1")
        self.assertTrue(slots[0]["healthy"])
        self.assertEqual(slots[0]["fail_count"], 0)

    def test_check_all_records_attempts(self):
        chain = FailoverChain([
            {"name": "ok", "base_url": "https://ok.com", "max_fail": 3},
        ])
        # Replace monitor with a mock
        mock_monitor = Mock(spec=HealthMonitor)
        mock_monitor.check.return_value = True
        mock_monitor.fail_count = 0
        mock_monitor.max_fail = 3
        chain._slots[0].monitor = mock_monitor

        results = chain.check_all()
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(len(chain.attempts), 1)

    def test_attempt_healthy_provider(self):
        chain = FailoverChain([
            {"name": "p1", "base_url": "https://a.com"},
        ])
        attempt = chain.attempt()
        self.assertTrue(attempt.success)
        self.assertEqual(attempt.provider_name, "p1")

    def test_attempt_no_healthy(self):
        chain = FailoverChain([
            {"name": "p1", "base_url": "https://a.com", "max_fail": 1},
        ])
        chain._slots[0].monitor._fail_count = 1
        attempt = chain.attempt()
        self.assertFalse(attempt.success)
        self.assertIn("unhealthy", attempt.error)

    def test_reset_all(self):
        chain = FailoverChain([
            {"name": "p1", "base_url": "https://a.com", "max_fail": 1},
            {"name": "p2", "base_url": "https://b.com", "max_fail": 1},
        ])
        for slot in chain._slots:
            slot.monitor._fail_count = 1
        chain.reset_all()
        for slot in chain._slots:
            self.assertEqual(slot.monitor.fail_count, 0)

    def test_cursor_advances(self):
        chain = FailoverChain([
            {"name": "p1", "base_url": "https://a.com", "max_fail": 3},
            {"name": "p2", "base_url": "https://b.com", "max_fail": 3},
        ])
        first = chain.next_healthy()
        self.assertEqual(first.name, "p1")  # type: ignore[union-attr]
        second = chain.next_healthy()
        self.assertEqual(second.name, "p2")  # type: ignore[union-attr]

    def test_attempt_records_to_history(self):
        chain = FailoverChain([
            {"name": "p1", "base_url": "https://a.com"},
        ])
        chain.attempt()
        self.assertEqual(len(chain.attempts), 1)
        self.assertTrue(chain.attempts[0].success)


if __name__ == "__main__":
    unittest.main()
