"""Compatibility CLI for the reusable TCGplayer set-catalog service."""

from __future__ import annotations

import os
import sys

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.services.tcgplayer_set_catalog_service import *  # noqa: F403
from backend.services.tcgplayer_set_catalog_service import main


if __name__ == "__main__":
    raise SystemExit(main())
