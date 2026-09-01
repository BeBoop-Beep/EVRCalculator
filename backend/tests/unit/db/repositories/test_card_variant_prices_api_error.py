from postgrest.exceptions import APIError

from backend.db.repositories import card_variant_prices_repository as repository


class _Query:
    def select(self, *_args): return self
    def in_(self, *_args): return self
    def eq(self, *_args): return self
    def execute(self):
        raise APIError({"message": "schema cache unavailable", "code": "PGRST002", "hint": None, "details": None})


class _Client:
    def table(self, _name): return _Query()


def test_postgrest_failure_is_not_replaced_by_apierror_nameerror(monkeypatch):
    monkeypatch.setattr(repository, "create_client", lambda *_args: _Client())
    try:
        repository.get_latest_prices_for_variants(["variant-1"], "condition-1")
    except Exception as exc:
        assert isinstance(exc, APIError)
        assert not isinstance(exc, NameError)
        assert exc.code == "PGRST002"
    else:  # pragma: no cover
        raise AssertionError("expected the real PostgREST failure")

