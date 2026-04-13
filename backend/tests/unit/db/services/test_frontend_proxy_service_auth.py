from backend.db.services import frontend_proxy_service as service


def test_login_user_uses_isolated_auth_client_for_sign_in(monkeypatch):
    shared_sign_in_calls = []
    isolated_sign_in_calls = []

    class SharedAuth:
        def sign_in_with_password(self, _credentials):
            shared_sign_in_calls.append(True)
            raise AssertionError("shared auth client should not be used for login")

    class IsolatedAuth:
        def sign_in_with_password(self, credentials):
            isolated_sign_in_calls.append(credentials)

            class AuthResponse:
                user = type(
                    "User",
                    (),
                    {
                        "id": "user-123",
                        "email": credentials["email"],
                        "user_metadata": {"username": "collector-user"},
                    },
                )()

            return AuthResponse()

    class IsolatedClient:
        auth = IsolatedAuth()

    class QueryResult:
        data = [{"username": "collector-user", "email": "collector@example.com"}]

    class QueryBuilder:
        def select(self, _fields):
            return self

        def eq(self, _field, _value):
            return self

        def limit(self, _count):
            return self

        def execute(self):
            return QueryResult()

    class SharedClient:
        auth = SharedAuth()

        def table(self, _name):
            return QueryBuilder()

    monkeypatch.setattr(service, "supabase", SharedClient())
    monkeypatch.setattr(service, "_create_auth_client", lambda: IsolatedClient())
    monkeypatch.setattr(service, "issue_token", lambda user_id, email, name: f"token:{user_id}:{email}:{name}")

    payload, status = service.login_user("collector@example.com", "secret")

    assert status == 200
    assert payload["id"] == "user-123"
    assert payload["email"] == "collector@example.com"
    assert payload["name"] == "collector-user"
    assert payload["token"] == "token:user-123:collector@example.com:collector-user"
    assert len(shared_sign_in_calls) == 0
    assert isolated_sign_in_calls == [{"email": "collector@example.com", "password": "secret"}]


def test_signup_user_uses_isolated_auth_client_for_sign_up(monkeypatch):
    shared_sign_up_calls = []
    isolated_sign_up_calls = []

    class SharedAuth:
        def sign_up(self, _payload):
            shared_sign_up_calls.append(True)
            raise AssertionError("shared auth client should not be used for signup")

    class IsolatedAuth:
        def sign_up(self, payload):
            isolated_sign_up_calls.append(payload)

            class AuthResponse:
                user = type("User", (), {"id": "user-123"})()
                session = None

            return AuthResponse()

    class IsolatedClient:
        auth = IsolatedAuth()

    class QueryBuilder:
        def upsert(self, _payload, on_conflict=None):
            return self

        def execute(self):
            return type("Result", (), {"data": []})()

    class SharedClient:
        auth = SharedAuth()

        def table(self, _name):
            return QueryBuilder()

    monkeypatch.setattr(service, "supabase", SharedClient())
    monkeypatch.setattr(service, "_create_auth_client", lambda: IsolatedClient())

    payload, status = service.signup_user("Collector User", "collector@example.com", "secret")

    assert status == 201
    assert payload["requiresEmailConfirmation"] is True
    assert payload["user"]["email"] == "collector@example.com"
    assert len(shared_sign_up_calls) == 0
    assert isolated_sign_up_calls == [
        {
            "email": "collector@example.com",
            "password": "secret",
            "options": {"data": {"username": "Collector User"}},
        }
    ]


def test_get_me_prefers_profile_display_name_for_canonical_name(monkeypatch):
    def fake_decode_token(_token):
        return (
            {
                "id": "user-123",
                "email": "collector@example.com",
                "username": "collector-user",
            },
            None,
        )

    def fake_get_profile_by_user_id(_user_id, _email=None, username_hint=None):
        return (
            {
                "id": "user-123",
                "email": "collector@example.com",
                "username": "collector-user",
                "display_name": "Collector Prime",
            },
            None,
        )

    monkeypatch.setattr(service, "decode_token", fake_decode_token)
    monkeypatch.setattr(service, "get_profile_by_user_id", fake_get_profile_by_user_id)

    payload, status = service.get_me("token")

    assert status == 200
    assert payload["user"]["id"] == "user-123"
    assert payload["user"]["email"] == "collector@example.com"
    assert payload["user"]["username"] == "collector-user"
    assert payload["user"]["display_name"] == "Collector Prime"
    assert payload["user"]["name"] == "Collector Prime"


def test_get_me_falls_back_to_username_when_display_name_missing(monkeypatch):
    def fake_decode_token(_token):
        return (
            {
                "id": "user-123",
                "email": "collector@example.com",
            },
            None,
        )

    def fake_get_profile_by_user_id(_user_id, _email=None, username_hint=None):
        return (
            {
                "id": "user-123",
                "email": "collector@example.com",
                "username": "collector-user",
                "display_name": None,
            },
            None,
        )

    monkeypatch.setattr(service, "decode_token", fake_decode_token)
    monkeypatch.setattr(service, "get_profile_by_user_id", fake_get_profile_by_user_id)

    payload, status = service.get_me("token")

    assert status == 200
    assert payload["user"]["display_name"] is None
    assert payload["user"]["username"] == "collector-user"
    assert payload["user"]["name"] == "collector-user"


def test_get_me_returns_401_when_decode_fails(monkeypatch):
    def fake_decode_token(_token):
        return None, ({"message": "Not authenticated"}, 401)

    monkeypatch.setattr(service, "decode_token", fake_decode_token)

    payload, status = service.get_me(None)

    assert status == 401
    assert payload["message"] == "Not authenticated"


def test_get_current_profile_uses_token_fallback_when_profile_not_found(monkeypatch):
    def fake_decode_token(_token):
        return (
            {
                "id": "user-123",
                "email": "collector@example.com",
                "username": "collector-user",
                "display_name": "Collector Prime",
            },
            None,
        )

    def fake_get_profile_by_user_id(_user_id, _email=None, username_hint=None):
        return None, "Profile not found"

    def fake_get_me(_token):
        return (
            {
                "user": {
                    "id": "user-123",
                    "email": "collector@example.com",
                    "username": "collector-user",
                    "display_name": "Collector Prime",
                }
            },
            200,
        )

    monkeypatch.setattr(service, "decode_token", fake_decode_token)
    monkeypatch.setattr(service, "get_profile_by_user_id", fake_get_profile_by_user_id)
    monkeypatch.setattr(service, "get_me", fake_get_me)

    payload, status = service.get_current_profile("token")

    assert status == 200
    assert payload["profile"]["id"] == "user-123"
    assert payload["profile"]["username"] == "collector-user"
    assert payload["profile"]["display_name"] == "Collector Prime"
    assert payload["profile_warning"] == "PROFILE_FROM_TOKEN_FALLBACK"


def test_get_current_profile_uses_token_fallback_on_lookup_exception(monkeypatch):
    def fake_decode_token(_token):
        return (
            {
                "id": "user-123",
                "email": "collector@example.com",
                "username": "collector-user",
            },
            None,
        )

    def fake_get_profile_by_user_id(_user_id, _email=None, username_hint=None):
        raise RuntimeError("db timeout")

    def fake_get_me(_token):
        return (
            {
                "user": {
                    "id": "user-123",
                    "email": "collector@example.com",
                    "username": "collector-user",
                    "display_name": None,
                }
            },
            200,
        )

    monkeypatch.setattr(service, "decode_token", fake_decode_token)
    monkeypatch.setattr(service, "get_profile_by_user_id", fake_get_profile_by_user_id)
    monkeypatch.setattr(service, "get_me", fake_get_me)

    payload, status = service.get_current_profile("token")

    assert status == 200
    assert payload["profile"]["id"] == "user-123"
    assert payload["profile"]["email"] == "collector@example.com"
    assert payload["profile"]["username"] == "collector-user"
    assert payload["profile_warning"] == "PROFILE_FROM_TOKEN_FALLBACK"


def test_get_current_profile_normalizes_profile_username(monkeypatch):
    def fake_decode_token(_token):
        return (
            {
                "id": "user-123",
                "email": "collector@example.com",
            },
            None,
        )

    def fake_get_profile_by_user_id(_user_id, _email=None, username_hint=None):
        return (
            {
                "id": "user-123",
                "email": "collector@example.com",
                "username": "Collector Prime",
                "display_name": "Collector Prime",
            },
            None,
        )

    monkeypatch.setattr(service, "decode_token", fake_decode_token)
    monkeypatch.setattr(service, "get_profile_by_user_id", fake_get_profile_by_user_id)

    payload, status = service.get_current_profile("token")

    assert status == 200
    assert payload["profile"]["username"] == "collector-prime"
