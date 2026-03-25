from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
# Use service role key for backend operations (bypasses RLS policies)
# Falls back to anon key if service role key not available
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL and either SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY must be set in the environment")

try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    # Clear the schema cache to avoid stale schema issues
    if hasattr(supabase, 'postgrest') and hasattr(supabase.postgrest, '_cache'):
        supabase.postgrest._cache.clear()
except Exception as e:
    # Workaround for new sb_publishable key format in older SDK versions
    # For now, continue without Supabase connection
    print("Warning: Supabase client initialization failed (API key format incompatible)")
    supabase = None


def clear_schema_cache():
    """Clear the Supabase schema cache to avoid stale schema issues"""
    if supabase and hasattr(supabase, 'postgrest') and hasattr(supabase.postgrest, '_cache'):
        supabase.postgrest._cache.clear()
