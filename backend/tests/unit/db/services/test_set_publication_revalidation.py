import json
from contextlib import contextmanager

from backend.db.services import set_publication_revalidation as revalidation


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_notify_is_noop_when_unconfigured(monkeypatch):
    monkeypatch.delenv("SET_REVALIDATION_URL", raising=False)
    monkeypatch.delenv("SET_REVALIDATION_SECRET", raising=False)
    called = []
    monkeypatch.setattr(revalidation.urllib.request, "urlopen", lambda *_a, **_k: called.append(1))

    assert revalidation.notify_set_snapshot_published("alpha", "uuid-1") is False
    assert called == []


def test_notify_posts_with_secret_and_dedupes_identifiers(monkeypatch):
    monkeypatch.setenv("SET_REVALIDATION_URL", "https://example.test/api/internal/revalidate-set")
    monkeypatch.setenv("SET_REVALIDATION_SECRET", "s3cret")
    requests = []

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        return _FakeResponse()

    monkeypatch.setattr(revalidation.urllib.request, "urlopen", fake_urlopen)

    ok = revalidation.notify_set_snapshot_published("alpha", "alpha", None, "uuid-1", windows=["365d"])

    assert ok is True
    # Deduped: "alpha" once + "uuid-1"; None dropped.
    assert len(requests) == 2
    first = requests[0]
    assert first.get_header("X-revalidate-secret") == "s3cret"
    body = json.loads(first.data.decode("utf-8"))
    assert body == {"setId": "alpha", "windows": ["365d"]}


def test_notify_never_raises_on_transport_error(monkeypatch):
    monkeypatch.setenv("SET_REVALIDATION_URL", "https://example.test/api/internal/revalidate-set")
    monkeypatch.setenv("SET_REVALIDATION_SECRET", "s3cret")

    def boom(*_a, **_k):
        raise ConnectionError("network down")

    monkeypatch.setattr(revalidation.urllib.request, "urlopen", boom)

    # Best-effort: a cache-bust failure must never fail the publish.
    assert revalidation.notify_set_snapshot_published("alpha") is False


# ---------------------------------------------------------------------------
# Visible publication diagnostics.
#
# Tagged seed invalidation stays best-effort and non-fatal, but it must no
# longer be silent: an unconfigured run and a fully successful run used to
# produce identical (empty) evidence, which is why "the row was rebuilt but the
# page still shows the previous market date" had nothing to inspect.
# ---------------------------------------------------------------------------

import backend.db.services.set_publication_revalidation as revalidation


def _reset():
    revalidation.reset_revalidation_diagnostics()


def test_diagnostics_record_an_unconfigured_run(monkeypatch):
    _reset()
    monkeypatch.delenv("SET_REVALIDATION_URL", raising=False)
    monkeypatch.delenv("SET_REVALIDATION_SECRET", raising=False)

    assert revalidation.notify_set_publication({"canonical_key": "pitchBlack"}, commit=True) is False

    diagnostics = revalidation.get_revalidation_diagnostics()
    assert diagnostics["configured"] is False
    assert diagnostics["sets_considered"] == 1
    assert diagnostics["sets_attempted"] == 1
    assert diagnostics["sets_succeeded"] == 0
    line = revalidation.format_revalidation_diagnostics()
    assert "cache_invalidation_configured=no" in line
    assert "tagged seeds were NOT invalidated" in line


def test_diagnostics_record_a_successful_invalidation(monkeypatch):
    _reset()
    monkeypatch.setenv("SET_REVALIDATION_URL", "http://frontend/api/internal/revalidate-set")
    monkeypatch.setenv("SET_REVALIDATION_SECRET", "secret")
    monkeypatch.setattr(revalidation, "notify_set_snapshot_published", lambda *_a, **_k: True)

    assert revalidation.notify_set_publication({"canonical_key": "pitchBlack"}, commit=True) is True

    diagnostics = revalidation.get_revalidation_diagnostics()
    assert diagnostics["configured"] is True
    assert diagnostics["sets_succeeded"] == 1
    assert diagnostics["failed_sets"] == []
    line = revalidation.format_revalidation_diagnostics()
    assert "cache_invalidation_configured=yes" in line
    assert "succeeded=1" in line
    assert "NOT invalidated" not in line


def test_diagnostics_name_the_sets_whose_invalidation_failed(monkeypatch):
    _reset()
    monkeypatch.setenv("SET_REVALIDATION_URL", "http://frontend/api/internal/revalidate-set")
    monkeypatch.setenv("SET_REVALIDATION_SECRET", "secret")
    monkeypatch.setattr(revalidation, "notify_set_snapshot_published", lambda *_a, **_k: False)

    revalidation.notify_set_publication({"canonical_key": "pitchBlack"}, commit=True)
    revalidation.notify_set_publication({"canonical_key": "temporalForces"}, commit=True)

    line = revalidation.format_revalidation_diagnostics()
    assert "failed=2" in line
    assert "failed_sets=pitchBlack,temporalForces" in line


def test_a_dry_run_never_touches_the_cache_and_says_so():
    _reset()

    assert revalidation.notify_set_publication({"canonical_key": "pitchBlack"}, commit=False) is False

    diagnostics = revalidation.get_revalidation_diagnostics()
    assert diagnostics["sets_attempted"] == 0
    assert diagnostics["sets_skipped_dry_run"] == 1
    assert "skipped_dry_run=1" in revalidation.format_revalidation_diagnostics()
