"""Single-instance exclusion for the daily run (belt and braces beside the cron-level `flock -n`)."""
from __future__ import annotations

import os
from pathlib import Path

try:  # POSIX (the VM)
    import fcntl
except ImportError:  # pragma: no cover - Windows developer machines
    fcntl = None
    import msvcrt


class AlreadyRunning(RuntimeError):
    pass


class SingleInstance:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fh = None

    def __enter__(self) -> "SingleInstance":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+")
        try:
            if fcntl is not None:
                fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:  # pragma: no cover
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self._fh.close()
            self._fh = None
            raise AlreadyRunning(str(self.path)) from exc
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(str(os.getpid()))
        self._fh.flush()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fh is not None:
            try:
                if fcntl is not None:
                    fcntl.flock(self._fh, fcntl.LOCK_UN)
                else:  # pragma: no cover
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                self._fh.close()
                self._fh = None
