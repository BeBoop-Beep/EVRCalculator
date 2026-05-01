from backend.db.services import waitlist_signup_service as waitlist_service


class _ExplodingSupabase:
    def table(self, _name):
        raise AssertionError("Database should not be touched for invalid email")


def test_insert_waitlist_signup_rejects_invalid_email_before_db(monkeypatch):
    monkeypatch.setattr(waitlist_service, "supabase", _ExplodingSupabase())

    result, error = waitlist_service.insert_waitlist_signup(" test@example.co ")

    assert result == {}
    assert error is not None
    assert error["status"] == "invalid_email"
    assert error["http_status"] == 400


def test_insert_waitlist_signup_normalizes_email_before_lookup(monkeypatch):
    captured = {}

    def _capture_lookup(email):
        captured["email"] = email
        return {"id": "abc", "email": email, "status": "active"}

    def _handle_existing(signup_row, source):
        return {"status": "already_exists", "message": "You're already on the list."}, None

    monkeypatch.setattr(waitlist_service, "_fetch_signup_by_email", _capture_lookup)
    monkeypatch.setattr(waitlist_service, "_handle_existing_signup", _handle_existing)

    result, error = waitlist_service.insert_waitlist_signup("  USER@EXAMPLE.COM  ", source="landing_page")

    assert error is None
    assert result["status"] == "already_exists"
    assert captured["email"] == "user@example.com"
