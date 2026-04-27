from concurrent.futures import ThreadPoolExecutor

from backend.db.services import frontend_proxy_service as service


def test_get_current_profile_is_stable_under_duplicate_concurrent_reads(monkeypatch):
    def fake_decode_token(_token):
        return (
            {
                "id": "user-123",
                "email": "collector@example.com",
            },
            None,
        )

    def fake_get_profile_by_user_id(_user_id, _email=None):
        return (
            {
                "id": "user-123",
                "email": "collector@example.com",
                "username": "collector-user",
                "display_name": "Collector User",
            },
            None,
        )

    monkeypatch.setattr(service, "decode_token", fake_decode_token)
    monkeypatch.setattr(service, "get_profile_by_user_id", fake_get_profile_by_user_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(service.get_current_profile, "token") for _ in range(2)]

    results = [future.result() for future in futures]

    for payload, status in results:
        assert status == 200
        assert isinstance(payload, dict)
        assert payload.get("profile", {}).get("id") == "user-123"
