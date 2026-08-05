import logging
import math
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import ClientOptions, create_client


def _has_malformed_quoted_value(line: str) -> bool:
    if "=" not in line:
        return False
    _, raw_value = line.split("=", 1)
    value = raw_value.strip()
    return bool(value and value[0] in {"'", '"'} and value[-1] != value[0])


logger = logging.getLogger(__name__)

backend_env_path = Path(__file__).resolve().parents[2] / ".env"
if backend_env_path.exists():
    env_lines = backend_env_path.read_text(encoding="utf-8").splitlines()
    if not any(_has_malformed_quoted_value(line.strip()) for line in env_lines):
        load_dotenv(dotenv_path=backend_env_path, override=False)
        logger.info("supabase_client: loaded backend .env from %s", backend_env_path)
    else:
        logger.warning("supabase_client: skipped loading malformed backend .env at %s", backend_env_path)
else:
    load_dotenv(override=False)
    logger.info("supabase_client: loaded environment using default dotenv lookup")

SUPABASE_URL = os.getenv("SUPABASE_URL")
# Use service role key for backend operations (bypasses RLS policies)
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

logger.info(
    "supabase_client: env presence SUPABASE_URL=%s SUPABASE_SERVICE_ROLE_KEY=%s SUPABASE_ANON_KEY=%s JWT_SECRET=%s",
    bool(SUPABASE_URL),
    bool(SUPABASE_KEY),
    bool(os.getenv("SUPABASE_ANON_KEY")),
    bool(os.getenv("JWT_SECRET")),
)

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in the environment")

_PUBLIC_READ_TIMEOUT_SECONDS = 20

# --- service-role (publication / snapshot write) PostgREST timeout -----------
# Every service-role client previously relied on whatever implicit default the
# installed supabase-py happened to ship. An implicit default is not a contract:
# it changes with a dependency bump, it is invisible in the operational runbook,
# and a publication run that hangs on one PostgREST call has no stated upper
# bound. This makes the bound EXPLICIT and FINITE.
#
# `postgrest_client_timeout` is handed straight to the PostgREST session's
# httpx client (SyncPostgrestClient -> BasePostgrestClient.create_session ->
# httpx.Client(timeout=...)), so it bounds every request that session issues:
# SELECTs, upserts, and `.rpc(...)` publication calls alike. Reads AND writes.
SERVICE_ROLE_TIMEOUT_ENV_VAR = "SUPABASE_SERVICE_ROLE_POSTGREST_TIMEOUT_SECONDS"
DEFAULT_SERVICE_ROLE_TIMEOUT_SECONDS = 60.0


class InvalidServiceRoleTimeout(RuntimeError):
    """The configured service-role PostgREST timeout is unusable."""


def resolve_service_role_timeout_seconds(raw_value=None):
    """Parse the configured service-role timeout into a finite positive float.

    Fails LOUDLY rather than falling back. A misconfigured timeout that silently
    reverted to "no explicit bound" would reintroduce exactly the unbounded call
    this setting exists to prevent, and it would do so invisibly.
    """
    if raw_value is None:
        return DEFAULT_SERVICE_ROLE_TIMEOUT_SECONDS

    text = str(raw_value).strip()
    if not text:
        raise InvalidServiceRoleTimeout(
            f"{SERVICE_ROLE_TIMEOUT_ENV_VAR} is set but empty; "
            f"unset it to use the {DEFAULT_SERVICE_ROLE_TIMEOUT_SECONDS}s default "
            f"or give it a positive number of seconds"
        )
    try:
        seconds = float(text)
    except (TypeError, ValueError):
        raise InvalidServiceRoleTimeout(
            f"{SERVICE_ROLE_TIMEOUT_ENV_VAR}={text!r} is not a number of seconds"
        ) from None
    if math.isnan(seconds) or math.isinf(seconds):
        raise InvalidServiceRoleTimeout(
            f"{SERVICE_ROLE_TIMEOUT_ENV_VAR}={text!r} is not finite; an unbounded "
            f"publication request is never acceptable"
        )
    if seconds <= 0:
        raise InvalidServiceRoleTimeout(
            f"{SERVICE_ROLE_TIMEOUT_ENV_VAR}={text!r} must be greater than zero"
        )
    return seconds


SERVICE_ROLE_TIMEOUT_SECONDS = resolve_service_role_timeout_seconds(
    os.getenv(SERVICE_ROLE_TIMEOUT_ENV_VAR)
)
# Value only — never the URL, the key, or any header.
logger.info(
    "supabase_client: service-role PostgREST timeout resolved to %ss (env %s)",
    SERVICE_ROLE_TIMEOUT_SECONDS,
    SERVICE_ROLE_TIMEOUT_ENV_VAR,
)


def _service_role_options() -> ClientOptions:
    """Fresh ClientOptions for every service-role client.

    A new instance per client on purpose: ClientOptions carries a mutable
    `headers` dict, and `reset_service_role_auth` writes into it. Sharing one
    instance would let an auth swap on the module-level client silently follow
    every other service-role client built from it.
    """
    return ClientOptions(postgrest_client_timeout=SERVICE_ROLE_TIMEOUT_SECONDS)


try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY, options=_service_role_options())
    public_read_client = create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(postgrest_client_timeout=_PUBLIC_READ_TIMEOUT_SECONDS),
    )
    logger.info("supabase_client: supabase client initialized successfully")
    # Clear the schema cache to avoid stale schema issues
    if hasattr(supabase, 'postgrest') and hasattr(supabase.postgrest, '_cache'):
        supabase.postgrest._cache.clear()
except Exception as e:
    logger.exception("supabase_client: failed to initialize supabase client (%s)", type(e).__name__)
    raise RuntimeError(
        "Failed to initialize Supabase client. Verify SUPABASE_URL and "
        "SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY configuration."
    ) from e


def clear_schema_cache():
    """Clear the Supabase schema cache to avoid stale schema issues"""
    if supabase and hasattr(supabase, 'postgrest') and hasattr(supabase.postgrest, '_cache'):
        supabase.postgrest._cache.clear()


def create_service_role_client():
    """A service-role client with an EXPLICIT finite PostgREST timeout.

    Snapshot builders and the publication scripts all obtain their client here,
    so this is the single place that bound is applied. A timeout surfaces as an
    ordinary exception from `.execute()`; nothing here converts it into a
    success, a fresh result, or a matching generation marker.
    """
    return create_client(SUPABASE_URL, SUPABASE_KEY, options=_service_role_options())


def create_public_read_client():
    return create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(postgrest_client_timeout=_PUBLIC_READ_TIMEOUT_SECONDS),
    )


def reset_service_role_auth():
    auth_header = f"Bearer {SUPABASE_KEY}"
    # If auth is already the service-role key, skip tearing down the PostgREST
    # client.  Nulling _postgrest forces a full client rebuild on the next
    # supabase.table() call and is the primary cause of per-request latency on
    # the public-profile endpoint when no user token has been injected.
    current_auth = supabase.options.headers.get("Authorization", "")
    if current_auth == auth_header:
        return
    supabase.options.headers["Authorization"] = auth_header
    if hasattr(supabase, "auth") and hasattr(supabase.auth, "_headers"):
        supabase.auth._headers["Authorization"] = auth_header
    if hasattr(supabase, "_postgrest"):
        supabase._postgrest = None
    if hasattr(supabase, "_storage"):
        supabase._storage = None
    if hasattr(supabase, "_functions"):
        supabase._functions = None
