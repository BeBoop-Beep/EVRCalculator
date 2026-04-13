from backend.db.services import public_identity_service as service


class _Query:
    def __init__(self, dataset):
        self._dataset = dataset
        self._operator = None
        self._candidate = None

    def select(self, _fields):
        return self

    def limit(self, _count):
        return self

    def eq(self, _column, candidate):
        self._operator = "eq"
        self._candidate = candidate
        return self

    def ilike(self, _column, candidate):
        self._operator = "ilike"
        self._candidate = candidate
        return self

    def execute(self):
        if self._operator == "eq":
            rows = [row for row in self._dataset if row.get("username") == self._candidate]
        elif self._operator == "ilike":
            rows = [row for row in self._dataset if str(row.get("username") or "").lower() == str(self._candidate or "").lower()]
        else:
            rows = []

        class _Result:
            def __init__(self, data):
                self.data = data

        return _Result(rows[:1])


class _SupabaseStub:
    def __init__(self, dataset):
        self._dataset = dataset

    def table(self, _name):
        return _Query(self._dataset)


def test_normalize_profile_username_returns_slug_for_raw_profile_username():
    profile = {
        "id": "user-123",
        "username": "Donald Stivison Jr",
        "display_name": "Dengkee",
    }

    normalized = service.normalize_profile_username(profile)

    assert normalized["username"] == "donald-stivison-jr"


def test_resolve_public_user_by_username_finds_legacy_spaced_username(monkeypatch):
    monkeypatch.setattr(
        service,
        "supabase",
        _SupabaseStub(
            [
                {
                    "id": "user-123",
                    "username": "Donald Stivison Jr",
                    "display_name": "Dengkee",
                    "is_profile_public": True,
                }
            ]
        ),
    )

    user, trace = service.resolve_public_user_by_username("donald-stivison-jr", correlation_id="corr-1")

    assert user["id"] == "user-123"
    assert trace["row_found"] is True
    assert trace["lookup_strategy"] == "username_ilike_spaced"
