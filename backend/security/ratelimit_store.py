"""Pluggable counters for the rate limiter.

* ``MemoryStore``  per-process, used by tests and local development.
* ``UpstashStore`` shared across Vercel instances (Upstash Redis REST API, stdlib only).

Both implement ``hit(key, window_s) -> (count, retry_after_s)`` as a fixed window.
If the shared store is unreachable we fail OPEN (log + allow) so an outage cannot lock
every user out; login paths can opt into fail-closed later via ``fail_closed=True``.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request
from urllib.parse import urlsplit
from typing import Protocol

log = logging.getLogger("kpt.ratelimit")


class Store(Protocol):
    def hit(self, key: str, window_s: int) -> tuple[int, int]: ...


class MemoryStore:
    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, window_s: int) -> tuple[int, int]:
        now = time.time()
        with self._lock:
            start, count = self._windows.get(key, (now, 0))
            if now - start >= window_s:
                start, count = now, 0
            count += 1
            self._windows[key] = (start, count)
            if len(self._windows) > 5000:
                for k in [k for k, (s, _) in self._windows.items() if now - s >= window_s]:
                    del self._windows[k]
            return count, max(1, int(window_s - (now - start)))


_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def validate_rest_url(url: str) -> str:
    """Return the base URL if it is safe to send the bearer token to, otherwise raise ValueError (never echoed).

    Only ``https://host`` is accepted; plain ``http://`` is allowed for loopback hosts only (local fakes, tests).
    ``file:``, ``ftp:``, custom schemes, URLs without a host and URLs with embedded credentials are refused, so
    ``urllib`` can never be pointed at a local file or an unencrypted remote endpoint through configuration.
    """
    parts = urlsplit(str(url or "").strip())
    host = (parts.hostname or "").lower()
    if not host or parts.username or parts.password:
        raise ValueError("rate-limit store URL needs a host and no embedded credentials")
    if parts.scheme == "https" or (parts.scheme == "http" and host in _LOOPBACK_HOSTS):
        return str(url).strip().rstrip("/")
    raise ValueError("rate-limit store URL must use https (http only for loopback)")


class UpstashStore:
    def __init__(self, url: str, token: str, fail_closed: bool = False, timeout_s: float = 1.5) -> None:
        self.url, self.token = validate_rest_url(url), token
        self.fail_closed, self.timeout = fail_closed, timeout_s

    def hit(self, key: str, window_s: int) -> tuple[int, int]:
        body = json.dumps([["INCR", key], ["EXPIRE", key, window_s, "NX"], ["TTL", key]]).encode()
        req = urllib.request.Request(f"{self.url}/pipeline", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            # URL scheme/host were checked by validate_rest_url() in __init__
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310  # nosec B310
                out = json.loads(resp.read())
            return int(out[0]["result"]), max(1, int(out[2]["result"]))
        except Exception:  # noqa: BLE001 - any failure of the shared store is handled the same way
            log.warning("rate-limit store unavailable; fail_closed=%s", self.fail_closed)
            return (10**9, window_s) if self.fail_closed else (0, window_s)
