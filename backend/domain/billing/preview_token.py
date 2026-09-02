import base64
import hashlib
import hmac
import json
import time

from .errors import PlanChangeNotAllowed

TOKEN_VERSION = 1


def _b64_encode(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64_decode(text: str) -> dict:
    padding = "=" * (-len(text) % 4)
    raw = base64.urlsafe_b64decode(text + padding)
    return json.loads(raw.decode("utf-8"))


def _signature(secret: str, visible_b64: str, hidden: dict) -> str:
    hidden_json = json.dumps(hidden, sort_keys=True)
    message = f"{visible_b64}|{hidden_json}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def sign_preview_token(*, secret: str, visible: dict, hidden: dict) -> str:
    visible_b64 = _b64_encode(visible)
    sig = _signature(secret, visible_b64, hidden)
    return f"v{TOKEN_VERSION}.{visible_b64}.{sig}"


def verify_preview_token(token: str, *, secret: str, hidden: dict, now: float | None = None) -> dict:
    try:
        version_part, visible_b64, sig = token.split(".", 2)
        if version_part != f"v{TOKEN_VERSION}":
            raise ValueError("unsupported token version")
        visible = _b64_decode(visible_b64)
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlanChangeNotAllowed("Malformed preview token") from exc

    expected_sig = _signature(secret, visible_b64, hidden)
    if not hmac.compare_digest(expected_sig, sig):
        raise PlanChangeNotAllowed("Preview token signature mismatch")

    expires_at = visible.get("expiresAt")
    if expires_at is None:
        raise PlanChangeNotAllowed("Preview token missing expiry")
    current_time = time.time() if now is None else now
    if current_time > expires_at:
        raise PlanChangeNotAllowed("Preview token expired")

    return visible
