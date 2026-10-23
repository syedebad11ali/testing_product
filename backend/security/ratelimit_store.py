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


class UpstashStore:
    def __init__(self, url: str, token: str, fail_closed: bool = False, timeout_s: float = 1.5) -> None:
        self.url, self.token, self.fail_closed, self.timeout = url.rstrip("/"), token, fail_closed, timeout_s

    def hit(self, key: str, window_s: int) -> tuple[int, int]:
        body = json.dumps([["INCR", key], ["EXPIRE", key, window_s, "NX"], ["TTL", key]]).encode()
        req = urllib.request.Request(f"{self.url}/pipeline", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (https URL from config)
                out = json.loads(resp.read())
            return int(out[0]["result"]), max(1, int(out[2]["result"]))
        except Exception:  # noqa: BLE001 - any failure of the shared store is handled the same way
            log.warning("rate-limit store unavailable; fail_closed=%s", self.fail_closed)
            return (10**9, window_s) if self.fail_closed else (0, window_s)
