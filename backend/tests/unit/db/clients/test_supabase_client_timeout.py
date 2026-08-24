"""The service-role PostgREST timeout must be EXPLICIT, FINITE and validated.

Why this exists
---------------
`service_read_client` always received an explicit 20s PostgREST timeout, but
`create_service_role_client()` — the client every snapshot builder and every
publication script uses — called `create_client(...)` with no options at all. Its
bound was therefore whatever the installed supabase-py happened to default to:
invisible in the runbook, silently changed by a dependency bump, and impossible
to state as an upper bound when a publication run appeared to hang.

These tests pin the contract. No real Supabase call is ever made: `create_client`
is monkeypatched and the module is loaded as an ISOLATED copy so the process-wide
client other tests hold is never rebuilt underneath them.
"""

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

import pytest
import supabase as supabase_package

MODULE_PATH = (
    Path(__file__).resolve().parents[4] / "db" / "clients" / "supabase_client.py"
)

FAKE_URL = "https://project-under-test.supabase.co"
FAKE_SERVICE_KEY = "service-role-key-under-test"
FAKE_ANON_KEY = "anon-key-under-test"


def _load_isolated(monkeypatch, *, timeout_env=None, anon_key=FAKE_ANON_KEY):
    """Import a FRESH copy of supabase_client with create_client stubbed out.

    Returns ``(module, created)`` where ``created`` records one entry per
    `create_client` call: the url, the key, and the ClientOptions it received.
    """
    created = []

    def fake_create_client(url, key, options=None):
        created.append({"url": url, "key": key, "options": options})
        # Deliberately bare: the module's optional `hasattr(...)` schema-cache
        # cleanup must cope with a client that exposes no postgrest internals.
        return SimpleNamespace(options=options)

    monkeypatch.setattr(supabase_package, "create_client", fake_create_client)
    monkeypatch.setenv("SUPABASE_URL", FAKE_URL)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", FAKE_SERVICE_KEY)
    if anon_key is None:
        # Keep dotenv from repopulating the real local value during isolated
        # module import while still representing unusable configuration.
        monkeypatch.setenv("SUPABASE_ANON_KEY", "")
    else:
        monkeypatch.setenv("SUPABASE_ANON_KEY", anon_key)
    if timeout_env is None:
        monkeypatch.delenv(
            "SUPABASE_SERVICE_ROLE_POSTGREST_TIMEOUT_SECONDS", raising=False
        )
    else:
        monkeypatch.setenv(
            "SUPABASE_SERVICE_ROLE_POSTGREST_TIMEOUT_SECONDS", timeout_env
        )

    spec = importlib.util.spec_from_file_location(
        "supabase_client_under_test", str(MODULE_PATH)
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, created


# ---------------------------------------------------------------------------
# The default is finite
# ---------------------------------------------------------------------------
def test_the_default_service_role_timeout_is_finite_and_positive(monkeypatch):
    module, _created = _load_isolated(monkeypatch)

    resolved = module.SERVICE_ROLE_TIMEOUT_SECONDS
    assert resolved == 60.0
    assert math.isfinite(resolved)
    assert resolved > 0


def test_the_env_var_name_is_the_documented_one(monkeypatch):
    module, _created = _load_isolated(monkeypatch)
    assert (
        module.SERVICE_ROLE_TIMEOUT_ENV_VAR
        == "SUPABASE_SERVICE_ROLE_POSTGREST_TIMEOUT_SECONDS"
    )


def test_the_environment_override_is_honored(monkeypatch):
    module, created = _load_isolated(monkeypatch, timeout_env="  90.5  ")

    assert module.SERVICE_ROLE_TIMEOUT_SECONDS == 90.5
    service_role = created[0]  # the module-level write client
    assert service_role["options"].postgrest_client_timeout == 90.5


# ---------------------------------------------------------------------------
# Invalid configuration fails LOUDLY — never a silent unbounded fallback
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw",
    ["", "   ", "abc", "0", "0.0", "-1", "-0.5", "nan", "NaN", "inf", "-inf", "Infinity"],
)
def test_invalid_timeout_values_fail_clearly(raw):
    from backend.db.clients import supabase_client

    with pytest.raises(supabase_client.InvalidServiceRoleTimeout) as excinfo:
        supabase_client.resolve_service_role_timeout_seconds(raw)
    # The operator must be told which knob is wrong.
    assert "SUPABASE_SERVICE_ROLE_POSTGREST_TIMEOUT_SECONDS" in str(excinfo.value)


def test_an_unset_value_uses_the_default_rather_than_raising():
    from backend.db.clients import supabase_client

    assert supabase_client.resolve_service_role_timeout_seconds(None) == 60.0


def test_an_invalid_env_value_fails_during_module_initialization(monkeypatch):
    """Initialization must abort, not quietly revert to an unbounded client."""
    with pytest.raises(Exception) as excinfo:
        _load_isolated(monkeypatch, timeout_env="0")
    assert "SUPABASE_SERVICE_ROLE_POSTGREST_TIMEOUT_SECONDS" in str(excinfo.value)


def test_a_negative_env_value_fails_during_module_initialization(monkeypatch):
    with pytest.raises(Exception):
        _load_isolated(monkeypatch, timeout_env="-30")


# ---------------------------------------------------------------------------
# EVERY service-role client carries the resolved options
# ---------------------------------------------------------------------------
def test_the_module_level_write_client_receives_explicit_options(monkeypatch):
    module, created = _load_isolated(monkeypatch)

    module_level = created[0]
    assert module_level["options"] is not None, "the write client must not rely on an implicit default"
    assert module_level["options"].postgrest_client_timeout == 60.0


def test_every_create_service_role_client_receives_explicit_options(monkeypatch):
    module, created = _load_isolated(monkeypatch, timeout_env="45")
    created.clear()

    for _ in range(3):
        module.create_service_role_client()

    assert len(created) == 3
    for call in created:
        assert call["options"] is not None
        assert call["options"].postgrest_client_timeout == 45.0
        assert math.isfinite(call["options"].postgrest_client_timeout)


def test_each_service_role_client_gets_its_own_options_instance(monkeypatch):
    """ClientOptions carries a mutable headers dict that auth resets write into.

    Sharing one instance would let an auth swap on one client silently follow
    every other service-role client.
    """
    module, created = _load_isolated(monkeypatch)
    created.clear()

    module.create_service_role_client()
    module.create_service_role_client()

    first, second = created[0]["options"], created[1]["options"]
    assert first is not second
    assert first.headers is not second.headers


# ---------------------------------------------------------------------------
# Short-timeout service reads remain explicitly privileged
# ---------------------------------------------------------------------------
def test_the_short_timeout_service_reader_uses_service_role(monkeypatch):
    module, created = _load_isolated(monkeypatch, timeout_env="45")

    assert module._READ_TIMEOUT_SECONDS == 20
    service_read = created[1]  # the module-level service_read_client
    assert service_read["key"] == FAKE_SERVICE_KEY
    assert service_read["options"].postgrest_client_timeout == 20

    created.clear()
    module.create_short_timeout_service_client()
    assert created[0]["key"] == FAKE_SERVICE_KEY
    assert created[0]["options"].postgrest_client_timeout == 20


# ---------------------------------------------------------------------------
# Public reads are genuinely anon/RLS constrained
# ---------------------------------------------------------------------------
def test_public_read_client_uses_only_the_anon_credential(monkeypatch):
    module, created = _load_isolated(monkeypatch)
    created.clear()

    module.create_public_read_client()

    assert len(created) == 1
    assert created[0]["key"] == FAKE_ANON_KEY
    assert created[0]["key"] != FAKE_SERVICE_KEY
    assert created[0]["options"].postgrest_client_timeout == 20


def test_public_read_client_fails_closed_when_anon_key_is_missing(monkeypatch):
    # The public snapshot reader is initialized at module load, so missing
    # public credentials must abort startup before any anon client is created.
    with pytest.raises(Exception, match="SUPABASE_ANON_KEY"):
        _load_isolated(monkeypatch, anon_key=None)


def test_service_and_public_factories_never_share_credential_sources(monkeypatch):
    module, created = _load_isolated(monkeypatch)
    created.clear()

    module.create_service_role_client()
    module.create_short_timeout_service_client()
    module.create_public_read_client()

    assert [call["key"] for call in created] == [
        FAKE_SERVICE_KEY,
        FAKE_SERVICE_KEY,
        FAKE_ANON_KEY,
    ]


# ---------------------------------------------------------------------------
# A timeout stays a failure
# ---------------------------------------------------------------------------
def test_a_timeout_from_a_service_role_call_propagates_as_an_error(monkeypatch):
    """Nothing in this module converts a timeout into a usable result."""
    module, _created = _load_isolated(monkeypatch)

    class ReadTimeout(Exception):
        pass

    class _TimingOutTable:
        def upsert(self, *_a, **_k):
            return self

        def execute(self):
            raise ReadTimeout("timed out")

    client = module.create_service_role_client()
    client.table = lambda _name: _TimingOutTable()

    with pytest.raises(ReadTimeout):
        client.table("pokemon_set_page_snapshot_latest").upsert({}).execute()


def test_the_module_does_not_swallow_base_exceptions():
    """KeyboardInterrupt must never be caught by the initialization guard."""
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "except BaseException" not in source
    assert "except KeyboardInterrupt" not in source


# ---------------------------------------------------------------------------
# No secrets in the logs
# ---------------------------------------------------------------------------
def test_initialization_logs_the_timeout_but_no_secret(monkeypatch, caplog):
    with caplog.at_level("INFO"):
        module, _created = _load_isolated(monkeypatch, timeout_env="75")

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "75" in text, "the resolved timeout must be observable"
    assert FAKE_SERVICE_KEY not in text
    assert FAKE_ANON_KEY not in text
    assert FAKE_URL not in text
    assert "Authorization" not in text
    assert "Bearer" not in text


def test_the_timeout_bounds_reads_and_writes_alike(monkeypatch):
    """`postgrest_client_timeout` is the PostgREST session's httpx timeout.

    supabase-py hands it to SyncPostgrestClient, which hands it to
    BasePostgrestClient.create_session -> httpx.Client(timeout=...). One httpx
    client serves every request that session makes, so the bound covers SELECTs,
    upserts and `.rpc(...)` publication calls alike. Pinned here because the whole
    point of Part 1 is that publication WRITES are bounded, not just reads.
    """
    import inspect

    from postgrest.base_client import BasePostgrestClient

    source = inspect.getsource(BasePostgrestClient.__init__)
    assert "self.session = self.create_session(base_url, headers, timeout" in source

    module, created = _load_isolated(monkeypatch)
    assert created[0]["options"].postgrest_client_timeout == module.SERVICE_ROLE_TIMEOUT_SECONDS
