from __future__ import annotations

from typing import Any

__all__ = ["PackEVRSimulator", "calculate_pack_simulations"]


def __getattr__(name: str) -> Any:
    # Lazy export to avoid importing heavy simulation dependencies at package import time.
    if name in __all__:
        from .evrSimulator import PackEVRSimulator, calculate_pack_simulations

        return {
            "PackEVRSimulator": PackEVRSimulator,
            "calculate_pack_simulations": calculate_pack_simulations,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
