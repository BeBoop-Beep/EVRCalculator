from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.db.services import frontend_proxy_service as service


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.operation, self.payload = db, table, [], "select", None

    def select(self, *_args): return self
    def eq(self, key, value): self.filters.append((key, str(value), False)); return self
    def ilike(self, key, value): self.filters.append((key, str(value).lower(), True)); return self
    def limit(self, _value): return self
    def insert(self, payload): self.operation, self.payload = "insert", dict(payload); return self
    def execute(self):
        rows = self.db.rows.setdefault(self.table, [])
        if self.operation == "insert":
            if any(row.get("username") == self.payload.get("username") for row in rows):
                raise RuntimeError("unique username")
            rows.append(dict(self.payload))
            return Result([dict(self.payload)])
        found = []
        for row in rows:
            if all((str(row.get(key, "")).lower() == value if insensitive else str(row.get(key, "")) == value) for key, value, insensitive in self.filters):
                found.append(dict(row))
        return Result(found)


class DB:
    def __init__(self, rows=None): self.rows = {"users": list(rows or [])}
    def table(self, name): return Query(self, name)


def auth_user(user_id=None, email="person@example.com", metadata=None):
    return SimpleNamespace(id=user_id or str(uuid4()), email=email, user_metadata=metadata or {})


def test_new_verified_user_is_base_and_username_is_private():
    db, user = DB(), auth_user(metadata={"index_plan": "premium", "name": "Collector"})
    profile = service.ensure_app_profile_for_supabase_user(user, db_client=db)
    assert profile["id"] == user.id
    assert profile.get("index_plan") is None
    assert profile["username"].startswith("collector-")
    assert "person" not in profile["username"]
    assert "index_plan" not in db.rows["users"][0]


@pytest.mark.parametrize("plan", [None, "plus", "premium"])
def test_existing_profile_and_entitlement_are_preserved(plan):
    user = auth_user()
    original = {"id": user.id, "email": user.email, "username": "kept-name", "index_plan": plan, "display_name": "Kept"}
    profile = service.ensure_app_profile_for_supabase_user(user, db_client=DB([original]))
    assert profile["username"] == "kept-name"
    assert profile["display_name"] == "Kept"
    assert profile["index_plan"] == plan


def test_matching_email_with_different_uuid_fails_closed():
    user = auth_user()
    db = DB([{"id": str(uuid4()), "email": user.email, "username": "legacy"}])
    with pytest.raises(service.ProfileIdentityConflictError):
        service.ensure_app_profile_for_supabase_user(user, db_client=db)


def test_exchange_rejects_arbitrary_unverified_jwt(monkeypatch):
    auth = SimpleNamespace(get_user=lambda _token: (_ for _ in ()).throw(RuntimeError("invalid")))
    monkeypatch.setattr(service, "_create_auth_client", lambda: SimpleNamespace(auth=auth))
    payload, status = service.exchange_supabase_access_token("header.payload.signature")
    assert status == 401
    assert payload["code"] == "INVALID_SUPABASE_TOKEN"


def test_exchange_verified_user_uses_canonical_token_issuer(monkeypatch):
    user = auth_user()
    auth = SimpleNamespace(get_user=lambda token: SimpleNamespace(user=user) if token == "verified" else None)
    monkeypatch.setattr(service, "_create_auth_client", lambda: SimpleNamespace(auth=auth))
    monkeypatch.setattr(service, "ensure_app_profile_for_supabase_user", lambda _user: {"id": user.id, "email": user.email, "username": "collector-safe", "index_plan": None})
    monkeypatch.setattr(service, "issue_token", lambda *args: "app-jwt")
    payload, status = service.exchange_supabase_access_token("verified")
    assert (status, payload) == (200, {"token": "app-jwt"})
