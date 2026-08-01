from __future__ import annotations

import threading
from typing import Callable, Optional


class LeaseHeartbeat:
    """Supervise one claimed job lease and surface ownership loss synchronously."""

    def __init__(
        self, heartbeat: Callable[[], object], *,
        lease_seconds: int, interval_seconds: Optional[float] = None,
    ):
        self.heartbeat = heartbeat
        self.interval = interval_seconds or max(1.0, lease_seconds / 3.0)
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.lost_ownership = False
        self.failure: Optional[Exception] = None
        self.count = 0

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                result = self.heartbeat()
                self.count += 1
                if not result:
                    self.lost_ownership = True
                    return
            except Exception as exc:
                self.failure = exc
                return
            if self._stop.wait(self.interval):
                return

    def __enter__(self) -> "LeaseHeartbeat":
        self._thread = threading.Thread(target=self._run, name="pokemon-onboarding-heartbeat", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(1.0, self.interval + 1.0))
            if self._thread.is_alive():
                self.failure = RuntimeError("heartbeat thread did not stop")
