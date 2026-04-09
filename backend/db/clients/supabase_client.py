import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


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

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
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
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def reset_service_role_auth():
    auth_header = f"Bearer {SUPABASE_KEY}"
    supabase.options.headers["Authorization"] = auth_header
    if hasattr(supabase, "auth") and hasattr(supabase.auth, "_headers"):
        supabase.auth._headers["Authorization"] = auth_header
    if hasattr(supabase, "_postgrest"):
        supabase._postgrest = None
    if hasattr(supabase, "_storage"):
        supabase._storage = None
    if hasattr(supabase, "_functions"):
        supabase._functions = None
