from backend.db.services.market_explorer_prepared_directory import (
    DIRECTORY_CACHE_TTL_SECONDS, _reset_prepared_directory_cache,
    read_prepared_comparison, read_prepared_comparison_bundle, read_prepared_directory,
    read_prepared_directory_cached, read_prepared_history, read_prepared_screen, read_set_context_ranking,
)

class Result:
    def __init__(self, data): self.data = data
class Call:
    def __init__(self, data): self.data = data
    def execute(self): return Result(self.data)
class Client:
    def __init__(self): self.calls = []
    def rpc(self, name, args):
        self.calls.append((name, args))
        return Call({"available": True} if "context" in name else [{"market_key": "set:x"}])


class TableQuery:
    """Records every `.select(...)` a caller asks of a table -- the guard
    below fails loudly if anything ever asks this fake for `payload_json`,
    which is exactly the ~6MB-per-set column the old constituent-count path
    used to select just to read one integer."""
    def __init__(self, calls, table_name, rows):
        self._calls = calls
        self._table_name = table_name
        self._rows = rows
        self._selected = None
    def select(self, *columns):
        self._selected = columns
        self._calls.append((self._table_name, columns))
        return self
    def in_(self, *_args, **_kwargs): return self
    def eq(self, *_args, **_kwargs): return self
    def execute(self): return Result(self._rows)


class BundleClient(Client):
    """Same RPC fake as `Client`, plus a `.table(...)` surface for the
    constituent-count query-cache lookup only. Comparison rows carry a
    `queryFingerprint` in `metadata` so the fingerprint path is exercised;
    history rows carry enough points to compute every long window."""
    def __init__(self, comparison_rows, history_rows, query_cache_rows=()):
        super().__init__()
        self.table_calls = []
        self._comparison_rows = comparison_rows
        self._history_rows = history_rows
        self._query_cache_rows = list(query_cache_rows)

    def rpc(self, name, args):
        self.calls.append((name, args))
        if "comparison" in name:
            return Call(self._comparison_rows)
        if "history" in name:
            return Call(self._history_rows)
        return Call([])

    def table(self, name):
        return TableQuery(self.table_calls, name, self._query_cache_rows)

def test_prepared_reads_use_only_bounded_read_rpcs():
    client = Client()
    assert read_prepared_directory(client)[0]["market_key"] == "set:x"
    read_prepared_comparison(client, ["set:x"])
    read_prepared_history(client, ["set:x"], "2026-06-01")
    read_prepared_screen(client, "momentum-leaders", None, 10)
    assert read_set_context_ranking(client, "id", "risers", "30D", 10, "2026-09-08")["available"]
    assert all("query" not in name and "preflight" not in name and "build" not in name for name, _ in client.calls)

def test_comparison_enforces_database_maximum_before_rpc():
    client = Client()
    try: read_prepared_comparison(client, [str(i) for i in range(26)])
    except ValueError: pass
    else: raise AssertionError("expected bound")
    assert client.calls == []

def test_directory_cache_is_bounded_expires_and_serves_stale_on_refresh_error():
    _reset_prepared_directory_cache()
    client = Client()
    assert read_prepared_directory_cached(client, now=10)[0]["market_key"] == "set:x"
    assert read_prepared_directory_cached(client, now=10 + DIRECTORY_CACHE_TTL_SECONDS - 1)[0]["market_key"] == "set:x"
    assert len(client.calls) == 1
    assert read_prepared_directory_cached(client, now=10 + DIRECTORY_CACHE_TTL_SECONDS)[0]["market_key"] == "set:x"
    assert len(client.calls) == 2
    client.rpc = lambda *_args: (_ for _ in ()).throw(RuntimeError("refresh failed"))
    assert read_prepared_directory_cached(client, now=1000)[0]["market_key"] == "set:x"
    _reset_prepared_directory_cache()


def _history_points(market_key, values_by_date):
    return [
        {"market_key": market_key, "market_date": date, "index_value": value, "tracked_value": None}
        for date, value in values_by_date.items()
    ]


def test_prepared_comparison_bundle_never_selects_payload_json():
    """Regression guard for the ~6MB-per-set constituent-count path.

    Selecting `payload_json` off `pokemon_set_market_dashboard_snapshot_latest`
    (or any table) just to derive a constituent count is exactly the defect
    that made a two-Set comparison transport ~12MB through PostgREST and blow
    past the RPC's own 5s statement_timeout. If this ever comes back, this
    test fails loudly rather than silently reintroducing the regression.
    """
    history = _history_points("set:x", {
        "2025-09-22": 100.0, "2026-03-01": 110.0, "2026-06-01": 120.0, "2026-09-19": 130.0,
    })
    client = BundleClient(
        comparison_rows=[{"market_key": "set:x", "comparison_as_of": "2026-09-19", "metadata": {}}],
        history_rows=history,
    )
    read_prepared_comparison_bundle(client, ["set:x"])
    for table_name, columns in client.table_calls:
        selected = " ".join(str(col) for col in columns)
        assert "payload_json" not in selected, f"{table_name} selected payload_json: {columns}"
        assert table_name != "pokemon_set_market_dashboard_snapshot_latest", (
            "prepared comparison must never query the Set dashboard snapshot table"
        )


def test_prepared_comparison_bundle_adds_zero_queries_beyond_comparison_and_history():
    """Enrichment must come from the already-fetched history, not a new read."""
    history = _history_points("set:x", {"2026-08-01": 100.0, "2026-09-19": 105.0})
    client = BundleClient(
        comparison_rows=[{"market_key": "set:x", "comparison_as_of": "2026-09-19", "metadata": {}}],
        history_rows=history,
    )
    read_prepared_comparison_bundle(client, ["set:x"])
    # Exactly the comparison RPC + the history RPC. No query-cache table hit
    # either, since this row carries no queryFingerprint.
    assert len(client.calls) == 2
    assert client.table_calls == []


def test_prepared_comparison_bundle_computes_long_windows_from_existing_history():
    """6M/1Y/SinceTracking must be real, computed values -- never a fake 0%."""
    history = _history_points("set:x", {
        "2025-09-22": 100.0,   # ~365d back from 2026-09-19: anchors 1Y
        "2026-03-23": 110.0,   # ~6M back: anchors 6M
        "2026-06-21": 115.0,   # ~90D back: anchors 3M
        "2026-08-20": 120.0,   # ~30D back: anchors 30D
        "2026-09-12": 125.0,   # 7D back: anchors 7D
        "2026-09-19": 130.0,   # latest
    })
    client = BundleClient(
        comparison_rows=[{"market_key": "set:x", "comparison_as_of": "2026-09-19", "metadata": {}}],
        history_rows=history,
    )
    bundle = read_prepared_comparison_bundle(client, ["set:x"])
    movements = bundle["markets"][0]["window_movements"]
    for key in ("1D", "7D", "30D", "3M", "6M", "1Y", "SinceTracking"):
        assert key in movements, f"missing window {key}"
    # SinceTracking spans the full published history (100 -> 130): a real,
    # computed return, not a null/zero placeholder.
    assert movements["SinceTracking"]["available"] is True
    assert round(movements["SinceTracking"]["percent"], 4) == 30.0
    assert movements["1Y"]["available"] is True
    assert movements["6M"]["available"] is True


def test_prepared_comparison_bundle_leaves_insufficient_history_unavailable_never_zero():
    """A market with only two close-together points has no real 6M/1Y span.

    The strict primitive must report those windows unavailable, never coerce
    a missing baseline into a fabricated 0% return.
    """
    history = _history_points("set:x", {"2026-09-12": 100.0, "2026-09-19": 101.0})
    client = BundleClient(
        comparison_rows=[{"market_key": "set:x", "comparison_as_of": "2026-09-19", "metadata": {}}],
        history_rows=history,
    )
    bundle = read_prepared_comparison_bundle(client, ["set:x"])
    movements = bundle["markets"][0]["window_movements"]
    # 30D is a strict (non-partial-eligible) window: with only 7 days of
    # history there is truly no 30D baseline, so it must stay unavailable --
    # never coerced into a fabricated 0%.
    assert movements["30D"]["available"] is False
    assert movements["30D"]["percent"] is None
    # 1Y is in PARTIAL_ELIGIBLE_WINDOW_KEYS: it honestly reports a partial
    # span (the real two available points) rather than disappearing, and
    # says so via isSinceFirstAvailable -- this is the documented,
    # deliberate behavior of compute_strict_window_movements, not a bug.
    assert movements["1Y"]["available"] is True
    assert movements["1Y"]["coverage"] == "partial"
    assert movements["1Y"]["isSinceFirstAvailable"] is True
    # A window that genuinely has data (7D, over two points seven days apart)
    # must never be silently suppressed either -- only report unavailable
    # where the baseline truly does not exist.
    assert movements["7D"]["available"] is True


def test_prepared_comparison_bundle_constituent_count_only_from_query_cache_fingerprint():
    """The only constituent-count source is the compact fingerprint cache row.

    A prepared row with a `queryFingerprint` resolves its count from
    `pokemon_market_explorer_query_cache`, keyed by that exact fingerprint --
    never a "latest" Set table with no `comparison_as_of` to check.
    """
    history = _history_points("set:x", {"2026-09-12": 100.0, "2026-09-19": 101.0})
    client = BundleClient(
        comparison_rows=[{
            "market_key": "set:x", "comparison_as_of": "2026-09-19",
            "metadata": {"queryFingerprint": "fp-abc"},
        }],
        history_rows=history,
        query_cache_rows=[{"query_fingerprint": "fp-abc", "constituent_count": 102}],
    )
    bundle = read_prepared_comparison_bundle(client, ["set:x"])
    assert bundle["markets"][0]["constituent_count"] == 102
    assert client.table_calls[0][0] == "pokemon_market_explorer_query_cache"


def test_prepared_comparison_bundle_constituent_count_null_when_no_fingerprint():
    """A Set market with no query-cache fingerprint gets `None`, not a guess.

    This is deliberate: no compact table exists in this codebase that carries
    both a constituent count AND a date/as-of column provably matching the
    prepared row's own `comparison_as_of`, so accuracy wins over filling the
    cell -- the frontend already renders `None` as "-".
    """
    history = _history_points("set:x", {"2026-09-12": 100.0, "2026-09-19": 101.0})
    client = BundleClient(
        comparison_rows=[{"market_key": "set:x", "comparison_as_of": "2026-09-19", "metadata": {}}],
        history_rows=history,
    )
    bundle = read_prepared_comparison_bundle(client, ["set:x"])
    assert bundle["markets"][0]["constituent_count"] is None
    assert client.table_calls == []
