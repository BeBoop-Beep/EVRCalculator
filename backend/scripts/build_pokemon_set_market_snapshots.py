"""Coordinated Cards + Market Dashboard snapshot builder.

This is the canonical entrypoint for set movement rebuilds.  The legacy
market-dashboard command delegates to the same implementation so either
command receives the generation and parity guarantees.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.scripts.build_pokemon_market_dashboard_snapshots import main


if __name__ == "__main__":
    main()
