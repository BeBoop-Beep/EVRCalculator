"""Dedicated stable credential authority for active-supply seller HMACs."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from backend.pricing_pipeline.ebay_credentials import parse_env_file

ROOT = Path(__file__).resolve().parents[2]
KEY = "ACTIVE_SUPPLY_SELLER_HASH_KEY"


class ActiveSupplyCredentialUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ActiveSupplyCredentials:
    seller_hash_key: str
    source: str

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.seller_hash_key.encode()).hexdigest()

    def __repr__(self) -> str:
        return f"ActiveSupplyCredentials(source={self.source!r}, seller_hash_key=<redacted>)"

    __str__ = __repr__


def load_active_supply_credentials(
    env: Mapping[str, str] | None = None, *, repo_root: Path = ROOT,
) -> ActiveSupplyCredentials:
    candidates: list[tuple[str, Mapping[str, str]]] = [
        ("process-environment", env if env is not None else os.environ),
        ("backend/.env", parse_env_file(repo_root / "backend/.env")),
    ]
    for source, values in candidates:
        value = str(values.get(KEY) or "").strip()
        if value:
            if len(value) < 32:
                raise ActiveSupplyCredentialUnavailable(
                    f"{KEY} from {source} must contain at least 32 characters"
                )
            return ActiveSupplyCredentials(value, source)
    raise ActiveSupplyCredentialUnavailable(
        f"{KEY} not found in process environment or backend/.env"
    )
