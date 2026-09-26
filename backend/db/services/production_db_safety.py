"""Host-local maintenance hold. This is not a substitute for DB authorization.

The default state lives outside the Git checkout so deployment cannot clear an
incident hold. An explicit alternate path supports isolated tests and other
hosts. Application serving reads do not use this gate.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOLD_PATH = Path('/home/ubuntu/state/db-safety/hold.json')


def maintenance_hold_active() -> bool:
    path = Path(os.environ.get('INDEX_DB_SAFETY_HOLD_PATH') or DEFAULT_HOLD_PATH)
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True  # An unreadable safety state is not permission to proceed.
    return True


def require_maintenance_allowed() -> None:
    if maintenance_hold_active():
        raise RuntimeError('production_database_safety_hold_active')
