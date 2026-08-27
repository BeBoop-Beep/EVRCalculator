from backend.api.market_request_metrics import build_identity, is_market_path


def test_market_path_scope_is_surgical():
    assert is_market_path("/explore/set-value-market")
    assert is_market_path("/explore/card-market-movers")
    assert is_market_path("/tcgs/pokemon/sets/example/market/movers")
    assert not is_market_path("/explore/product-rankings/overall")
    assert not is_market_path("/tcgs/pokemon/sets/example/page")


def test_build_identity_prefers_render_commit(monkeypatch):
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    monkeypatch.setenv("GIT_SHA", "fallback")
    assert build_identity() == "abc123"
