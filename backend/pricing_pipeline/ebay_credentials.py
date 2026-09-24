"""Single production-safe eBay credential authority. Secrets are never printed, logged or committed.

Resolution order (first source that supplies BOTH keys wins):
  1. process environment (systemd/cron/CI-provided; the intended production path)
  2. backend/.env       (the VM's normal credential file, alongside the Supabase credentials)
  3. frontend/.env.local (local development fallback only; disabled with allow_frontend_fallback=False)
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[2]
KEYS = ("EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET")


class CredentialsUnavailable(RuntimeError):
    pass


def parse_env_file(path: Path) -> dict[str, str]:
    """Minimal dotenv parser. utf-8-sig tolerates the BOM that Windows editors leave on the first key."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        out[key] = value.strip().strip('"').strip("'")
    return out


def environment_of(client_id: str) -> str:
    """eBay App IDs embed the environment: `Name-App-PRD-...` (production) or `Name-App-SBX-...` (sandbox)."""
    match = re.search(r"-(PRD|SBX)-", client_id)
    return {"PRD": "PRODUCTION", "SBX": "SANDBOX"}.get(match.group(1), "UNKNOWN") if match else "UNKNOWN"


@dataclass(frozen=True)
class EbayCredentials:
    client_id: str
    client_secret: str
    source: str

    @property
    def environment(self) -> str:
        return environment_of(self.client_id)

    def as_mapping(self) -> dict[str, str]:
        return {"EBAY_CLIENT_ID": self.client_id, "EBAY_CLIENT_SECRET": self.client_secret}

    def __repr__(self) -> str:  # never expose values
        return f"EbayCredentials(source={self.source!r}, environment={self.environment!r}, client_id=<redacted:{len(self.client_id)}>, client_secret=<redacted>)"

    __str__ = __repr__


def load_ebay_credentials(env: Mapping[str, str] | None = None, *, repo_root: Path = ROOT,
                          allow_frontend_fallback: bool = True) -> EbayCredentials:
    candidates: list[tuple[str, Mapping[str, str]]] = [
        ("process-environment", env if env is not None else os.environ),
        ("backend/.env", parse_env_file(repo_root / "backend/.env")),
    ]
    if allow_frontend_fallback:
        candidates.append(("frontend/.env.local", parse_env_file(repo_root / "frontend/.env.local")))
    for source, values in candidates:
        if all(values.get(key) for key in KEYS):
            return EbayCredentials(values["EBAY_CLIENT_ID"], values["EBAY_CLIENT_SECRET"], source)
    raise CredentialsUnavailable("eBay credentials not found in process environment or backend/.env"
                                 + (" or frontend/.env.local" if allow_frontend_fallback else ""))


def credential_presence(repo_root: Path = ROOT) -> dict[str, str]:
    """Which sources currently hold both keys (booleans only; used by audits and VM checks)."""
    return {
        "process-environment": str(all(os.environ.get(k) for k in KEYS)).lower(),
        "backend/.env": str(all(parse_env_file(repo_root / "backend/.env").get(k) for k in KEYS)).lower(),
        "frontend/.env.local": str(all(parse_env_file(repo_root / "frontend/.env.local").get(k) for k in KEYS)).lower(),
    }
