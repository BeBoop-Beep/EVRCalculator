"""P0-A: /market/sealed must resolve set identifiers like every other set module.

Reproduction that motivated this file: a cold Market tab visit renders
"Sealed Market — unable to load / Retry" on EVERY set, while Set Value Trend,
Top Chase and Movers on the same page render fine from the same identifier.

The cause is not missing data. The browser sends the normalized (lowercased)
set identifier — `ascendedheroes`, not the `ascendedHeroes` canonical_key — and
/market/sealed was the one set-module route that hand-rolled its own
`canonical_key.eq.<id>` lookup instead of calling the shared
`resolve_pokemon_set_identifier`. `.eq.` is case-sensitive, so sealed 404s on an
identifier every sibling route accepts.

Measured against a live backend before the fix:

    id=ascendedHeroes  market/sealed         -> 200
    id=ascendedheroes  market/sealed         -> 404   <-- what the browser sends
    id=ascendedheroes  market/value-history  -> 200

Using the shared resolver also brings sealed under `run_public_read_with_retry`,
which is the established protection for a dead pooled socket and which sealed's
hand-rolled query bypassed entirely.
"""

import pytest

from backend.api import main as api_main


SET_UUID = "75cd439d-aaa2-41cb-86f3-2fefa5b26e29"


@pytest.fixture
def resolver_calls(monkeypatch):
    """Capture what the sealed route hands to the shared resolver."""
    calls = []

    def fake_resolve(set_id, *, client=None):
        calls.append(set_id)
        # The real resolver accepts UUID, canonical_key, pokemon_api_set_id,
        # exact name, and normalized/hyphenated slugs alike.
        normalized = str(set_id).lower().replace("-", "").replace(" ", "")
        if normalized in {"ascendedheroes", SET_UUID.replace("-", "")}:
            return {"id": SET_UUID, "canonical_key": "ascendedHeroes"}
        raise LookupError(f"unknown set {set_id}")

    monkeypatch.setattr(api_main, "resolve_pokemon_set_identifier", fake_resolve, raising=False)
    return calls


@pytest.fixture
def sealed_reads(monkeypatch):
    reads = []

    def fake_read(client, resolved_set_id):
        reads.append(resolved_set_id)
        return {"set": {"id": resolved_set_id, "canonicalKey": "ascendedHeroes"}, "history": []}

    monkeypatch.setattr(api_main, "read_sealed_market_snapshot", fake_read)
    return reads


@pytest.mark.parametrize(
    "identifier",
    [
        pytest.param("ascendedheroes", id="normalized-lowercase-what-the-browser-sends"),
        pytest.param("ascendedHeroes", id="canonical-key"),
        pytest.param(SET_UUID, id="uuid"),
    ],
)
def test_sealed_market_accepts_every_identifier_form_its_siblings_accept(
    identifier, resolver_calls, sealed_reads
):
    response = api_main.get_pokemon_set_sealed_market(identifier)

    # A JSONResponse here means an error status; a dict means the payload.
    assert isinstance(response, dict), (
        f"/market/sealed rejected identifier {identifier!r} that sibling set modules accept; "
        f"got {getattr(response, 'status_code', response)!r}"
    )
    assert sealed_reads == [SET_UUID], "sealed must read the snapshot by resolved UUID"


def test_sealed_market_uses_the_shared_resolver_not_a_hand_rolled_query(resolver_calls, sealed_reads):
    """The retry/identifier contract lives in the shared resolver.

    Bypassing it is what both broke case tolerance and dropped sealed out of
    `run_public_read_with_retry`'s dead-socket protection.
    """
    api_main.get_pokemon_set_sealed_market("ascendedheroes")
    assert resolver_calls == ["ascendedheroes"]
