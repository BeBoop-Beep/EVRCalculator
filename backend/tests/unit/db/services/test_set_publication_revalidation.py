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
