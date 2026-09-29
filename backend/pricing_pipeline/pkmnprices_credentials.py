"""Production-safe PkmnPrices credential authority.

Resolution order:
  1. process environment
  2. backend/.env
  3. frontend/.env.local (development fallback only)

The API key is never rendered by repr/str and callers can disable the frontend
fallback on production hosts.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from backend.pricing_pipeline.ebay_credentials import parse_env_file

ROOT = Path(__file__).resolve().parents[2]
KEY = "PKMNPRICES_API_KEY"


class CredentialsUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class PkmnPricesCredentials:
    api_key: str
    source: str

    def __repr__(self) -> str:
        return f"PkmnPricesCredentials(source={self.source!r}, api_key=<redacted>)"

    __str__ = __repr__


def load_pkmnprices_credentials(
    env: Mapping[str, str] | None = None,
    *,
    repo_root: Path = ROOT,
    allow_frontend_fallback: bool = True,
) -> PkmnPricesCredentials:
    candidates: list[tuple[str, Mapping[str, str]]] = [
        ("process-environment", env if env is not None else os.environ),
        ("backend/.env", parse_env_file(repo_root / "backend/.env")),
    ]
    if allow_frontend_fallback:
        candidates.append(("frontend/.env.local", parse_env_file(repo_root / "frontend/.env.local")))
    for source, values in candidates:
        value = str(values.get(KEY) or "").strip()
        if value:
            return PkmnPricesCredentials(value, source)
    raise CredentialsUnavailable(
        "PkmnPrices API key not found in process environment or backend/.env"
        + (" or frontend/.env.local" if allow_frontend_fallback else "")
    )


def credential_presence(repo_root: Path = ROOT) -> dict[str, str]:
    return {
        "process-environment": str(bool(os.environ.get(KEY))).lower(),
        "backend/.env": str(bool(parse_env_file(repo_root / "backend/.env").get(KEY))).lower(),
        "frontend/.env.local": str(bool(parse_env_file(repo_root / "frontend/.env.local").get(KEY))).lower(),
    }
