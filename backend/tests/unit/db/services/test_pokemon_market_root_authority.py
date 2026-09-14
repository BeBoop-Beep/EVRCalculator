"""Tests for the frozen Sep 10, 2026 public Market root authority.

Covers: historical boundary routing (Sep 8 unchanged, Sep 9 still resolves via
the certification-derived canonical cohort, Sep 10 exactly the frozen 106,
future dates also 106 until explicitly changed), and membership != certification
for the authority-table path (stale-but-approved stays a member,
certified-but-not-approved never becomes one, identity fingerprint stability).
"""
from __future__ import annotations

import hashlib
import json

from backend.db.services import pokemon_market_rollout_cohort as cohort


class _Query:
    def __init__(self, rows):
        self.rows = list(rows)

    def select(self, *_a, **_k):
        return self

    def eq(self, field, value):
        self.rows = [row for row in self.rows if str(row.get(field)) == str(value)]
        return self

    def lte(self, field, value):
        self.rows = [row for row in self.rows if row.get(field) is not None and str(row.get(field))[:10] <= str(value)[:10]]
        return self

    def in_(self, field, values):
        values = {str(v) for v in values}
        self.rows = [row for row in self.rows if str(row.get(field)) in values]
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, n):
        self.rows = self.rows[:n]
        return self

    def execute(self):
        return _Result(list(self.rows))


class _Result:
    def __init__(self, data):
        self.data = data


class _Client:
    def __init__(self, tables):
        self.tables = tables

    def table(self, name):
        return _Query(self.tables.get(name, []))


FROZEN_106 = [f"11111111-0000-0000-0000-{i:012d}" for i in range(106)]


def _authority_rows(ids, *, activated="2026-09-10", enabled=True, deactivated=None):
    return [
        {
            "set_id": set_id,
            "activated_market_date": activated,
            "deactivated_market_date": deactivated,
            "enabled": enabled,
        }
        for set_id in ids
    ]


def _members_view_rows(ids):
    return [
        {
            "set_id": set_id,
            "set_name": f"Set {set_id[-4:]}",
            "canonical_key": f"set-{set_id[-4:]}",
            "era_name": "Scarlet & Violet",
            "release_date": "2025-01-01",
            "market_scope": "standard",
            "canonical_market_date": "2026-09-10",
            "market_publication_ready": False,
            "current_certification_status": "unknown",
        }
        for set_id in ids
    ]


def _client_with_authority(ids, extra_tables=None):
    tables = {
        cohort.MARKET_ROOT_AUTHORITY_TABLE: _authority_rows(ids),
        cohort.MARKET_READY_VIEW: _members_view_rows(ids),
        cohort.MARKET_CERTIFICATION_VIEW: [],
        "sets": [],
        "eras": [],
    }
    if extra_tables:
        tables.update(extra_tables)
    return _Client(tables)


def test_resolve_market_root_ids_sep10_reads_only_authority_table():
    client = _client_with_authority(FROZEN_106)
    ids = cohort.resolve_market_root_ids(client, market_date="2026-09-10")
    assert ids == sorted(FROZEN_106)
    assert len(ids) == 106


def test_resolve_market_root_ids_future_date_still_106_until_explicitly_changed():
    client = _client_with_authority(FROZEN_106)
    ids = cohort.resolve_market_root_ids(client, market_date="2027-01-01")
    assert len(ids) == 106


def test_sep9_unchanged_uses_canonical_certification_derived_resolver(monkeypatch):
    called = {}

    def fake_canonical(client, *, market_date=None):
        called["market_date"] = market_date
        return [{"id": "legacy-a"}, {"id": "legacy-b"}]

    monkeypatch.setattr(cohort, "_canonical_market_root_cohort", fake_canonical)
    result = cohort.resolve_market_root_cohort(_Client({}), market_date="2026-09-09")
    assert called["market_date"] == "2026-09-09"
    assert [row["id"] for row in result] == ["legacy-a", "legacy-b"]


def test_sep8_uses_legacy_staged_resolver(monkeypatch):
    called = {}

    def fake_legacy(client, *, market_date=None):
        called["market_date"] = market_date
        return [{"id": "staged-a"}]

    monkeypatch.setattr(cohort, "_legacy_market_root_cohort", fake_legacy)
    result = cohort.resolve_market_root_cohort(_Client({}), market_date="2026-09-08")
    assert called["market_date"] == "2026-09-08"
    assert [row["id"] for row in result] == ["staged-a"]


def test_certification_never_alters_authority_membership_stale_stays_member():
    """An approved root that is PRICE_FRESHNESS_STALE (or uncertified) stays a member."""
    stale_cert = [
        {
            "set_id": FROZEN_106[0],
            "market_scope": "standard",
            "canonical_market_date": "2026-09-10",
            "set_value_certified": False,
            "top10_certified": False,
            "market_scope_certified": False,
            "price_freshness_certified": False,
            "current_certification_status": "PRICE_FRESHNESS_STALE",
        }
    ]
    client = _client_with_authority(
        FROZEN_106, extra_tables={cohort.MARKET_CERTIFICATION_VIEW: stale_cert}
    )
    cohort_rows = cohort.resolve_market_root_cohort(client, market_date="2026-09-10")
    ids = {row["id"] for row in cohort_rows}
    assert FROZEN_106[0] in ids
    assert len(ids) == 106
    row = next(r for r in cohort_rows if r["id"] == FROZEN_106[0])
    assert row["market_structural_certified"] is False
    assert row["market_current_certification_status"] == "PRICE_FRESHNESS_STALE"


def test_non_member_fully_certified_set_never_added():
    """A set NOT in the frozen 106 never becomes a member, no matter its certification."""
    outsider = "99999999-0000-0000-0000-000000000001"
    fully_certified_cert = [
        {
            "set_id": outsider,
            "market_scope": "standard",
            "canonical_market_date": "2026-09-10",
            "set_value_certified": True,
            "top10_certified": True,
            "market_scope_certified": True,
            "price_freshness_certified": True,
            "current_certification_status": "CURRENT",
        }
    ]
    client = _client_with_authority(
        FROZEN_106,
        extra_tables={
            cohort.MARKET_CERTIFICATION_VIEW: fully_certified_cert,
            cohort.MARKET_READY_VIEW: _members_view_rows(FROZEN_106) + _members_view_rows([outsider]),
        },
    )
    cohort_rows = cohort.resolve_market_root_cohort(client, market_date="2026-09-10")
    ids = {row["id"] for row in cohort_rows}
    assert outsider not in ids
    assert len(ids) == 106


def test_member_count_stays_106_and_fingerprint_stable_across_certification_fixtures():
    def fingerprint(ids):
        encoded = json.dumps(sorted(ids), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    client_no_cert = _client_with_authority(FROZEN_106)
    client_mixed_cert = _client_with_authority(
        FROZEN_106,
        extra_tables={
            cohort.MARKET_CERTIFICATION_VIEW: [
                {
                    "set_id": set_id,
                    "market_scope": "standard",
                    "set_value_certified": i % 2 == 0,
                    "top10_certified": False,
                    "market_scope_certified": True,
                    "price_freshness_certified": i % 3 == 0,
                    "current_certification_status": "CURRENT" if i % 2 == 0 else "PRICE_FRESHNESS_STALE",
                }
                for i, set_id in enumerate(FROZEN_106)
            ]
        },
    )

    ids_a = [row["id"] for row in cohort.resolve_market_root_cohort(client_no_cert, market_date="2026-09-10")]
    ids_b = [row["id"] for row in cohort.resolve_market_root_cohort(client_mixed_cert, market_date="2026-09-10")]

    assert len(ids_a) == len(ids_b) == 106
    assert fingerprint(ids_a) == fingerprint(ids_b)


def test_authority_ids_expected_106_fingerprint_matches_frozen_snapshot():
    """Regression guard against the actual reconstructed 106 identity list.

    The literal hash below matches the migration's seeded UUID set, computed
    via sha256(json.dumps(sorted(ids), sort_keys=True, separators=(",", ":"))).
    See the migration file and task report for the source query.
    """
    ids = [
        "03764ded-825a-45c0-8b15-ce100cff9552", "03bfd551-26be-423f-a4f2-9c4e936f3de3",
        "069f83b6-3028-4a00-ae8e-96ef2083a11d", "076aa350-5b36-4ff4-9095-fe4e95c01b79",
        "0cb8a5a6-5b5a-4288-aded-8b03f0fd9ded", "0d90b4ed-16a1-456c-81c6-83d2869d3846",
        "0f7e51e2-5a78-4500-9c9c-f690e934a069", "15fd93a2-82e3-4a5f-9f11-112cee192c95",
        "1c48d45b-199b-4925-bbfe-168c59faf66a", "1c7aa5c4-c8c9-4ae8-a1eb-d613f7e4b890",
        "1e5eb27b-53bb-490b-9edb-1ce98b3a4341", "202518a0-5e86-4949-b1cd-c1c8ad95b616",
        "212383a2-ed84-4a5e-af37-50814247a437", "250f0404-e380-42e7-9aec-385ca8290ad4",
        "262dcb31-b7af-423e-8b11-2b7ba469ff72", "26db83e5-986f-4b91-82f4-c993ad1a0aaf",
        "26fedb88-87d7-487a-9f01-528d603c682e", "27077ea7-cd5d-4ba7-ae66-e905e780f0fd",
        "279f849e-9de7-4ca3-a922-a4f92ba9d89b", "27f3eb48-9964-4a3f-9861-a434ae244697",
        "29901e65-a5d2-4e12-8e26-62216ed947ab", "29d1d610-11c5-479c-a9ff-dace7bb96f92",
        "2d477c9a-bb2c-42aa-ae25-7cd4ca0f2a4a", "2d6ec108-70b2-4698-a21a-1af39828004f",
        "2fed4a27-a176-4d60-a92a-3c8b15f81dfb", "332b2885-9354-4a29-ba52-03fca35594d1",
        "34a48f79-1bd3-4f1d-9e3c-758955be70ee", "3836457c-77dc-44b0-a72f-779b6dd78884",
        "3b753fb6-a465-4e68-8ad9-4e34e114d4b7", "3f3c7677-b876-4353-821e-6bdd610fd683",
        "46ab39a7-dd96-4a2d-af0f-44b868918114", "472f851c-2e41-4c80-b6fc-8478d1d92730",
        "476a8f1c-bd50-4ba7-a217-562015fee3d6", "488bda22-33b7-40d7-9fe1-b3f87c2d2204",
        "4b15f040-4351-41ea-90e1-c07eb1b2f4d6", "4b792f11-635a-4e2f-9f60-09aafe387a4a",
        "4c0902e8-fc57-4e07-82e1-e4bdb9fe9990", "4de777b3-396e-4f19-9d78-c054b296bedb",
        "5109f22e-0799-46b5-a4ad-8861d1cfefee", "5361a918-eb23-447e-a00e-e21493bc4320",
        "549f2297-a03b-4276-ad96-ad41a8bcef8f", "591a2b3e-2dc8-4e80-b42d-aec4f4b786e4",
        "5bb951fd-bb74-40d7-b496-cca5bf959515", "5d3d5c23-7098-4393-ad63-6ad9372aee30",
        "5e160c6d-8f0e-4694-bf72-1fc3b7f01e45", "5e99f658-39f0-4845-9228-db8db3965f32",
        "5ee1fc9a-a49e-4323-8aa7-43df6d3c8124", "65ee8536-af5a-4242-8a1f-9928c81f501b",
        "69d6d1be-f610-421b-b29c-c3348fe19518", "6b5aa766-ca92-4ca2-a750-6323bbd97d13",
        "6c5be923-95d0-46ee-86a4-61148fb5152a", "6c82fb37-b9b9-4961-a528-12556bd15417",
        "6d813ed0-f263-4294-a099-18f1d5c7bd81", "6e18dc34-5d2f-47b2-8595-e350ebd4a630",
        "70a8d8f3-9aee-4ac8-88e4-dfbca50652f4", "74043b01-c2d0-49ad-a86e-404b7579aa83",
        "759c09f8-8a1b-4212-be89-66088afa6893", "75cc9ef9-1099-4e47-8d09-17f416606865",
        "75cd439d-aaa2-41cb-86f3-2fefa5b26e29", "7705c538-c6c1-4846-8efc-4bf4650f92e0",
        "7a1b8de0-331f-4635-8512-b737da431f7d", "7a3dd188-4375-41af-94de-c5247fe0b1a6",
        "7c998bc2-6073-4461-8873-64d1b3e78930", "7e99a62d-57ab-4ef4-8338-576524fb8d0d",
        "7fed6bc2-a67f-47e1-a453-d8c4ff986947", "806b7046-4fd5-4259-be17-54b28381f034",
        "8158d0ae-0255-48f0-b189-d134035b72b0", "8938c853-2282-46d8-ba44-87584fa2c168",
        "8a2c6f1f-dff9-45d7-9ae2-61ad05e4cee7", "8b5fb7da-391e-477d-b46c-f99ae584e7d3",
        "8cd0a0f0-d17c-4a5c-bc52-47e1723e0699", "8f78267f-493b-4d60-a19e-587ae1f60f69",
        "8fe71704-0369-427a-ad32-4d173b43b1e1", "91442900-3949-4ba4-8398-9e3dc2db1fa6",
        "93212749-ce0e-498e-975e-7d947a3448ce", "950b9e19-eb8d-41bd-995f-01bdf98103b3",
        "965b3000-c483-4110-bb21-ff5ffe120564", "98301e8a-8aa3-43d8-a85b-908883264721",
        "9a59b345-59b0-4fc1-a4a3-5f79cb6f2310", "9d282514-6b63-48cd-bc25-9ce330632cd3",
        "9e777620-7479-41c4-84fb-17d2aea123bb", "a72c75bd-0d61-4643-b603-fef78425dcfa",
        "a8064dc8-57b9-4e6b-87fd-c0aa077fea7a", "a91d2dfa-fd33-44ff-ac12-f221b833a2e2",
        "b0d7bd6a-4e57-4495-b975-e132417cc071", "b3c96740-a4a9-4c3d-a8f6-81ed4584549d",
        "b4b34b61-ce48-4fc4-bd91-201a350b2600", "ba05227c-b7eb-4428-9e8e-ae70b52fe89f",
        "bd6207d5-eeb5-4e67-aceb-29cf9c2bd9b6", "be72ec5d-de1a-41db-81e0-89c310ed75ae",
        "be7c981b-c55e-4f60-a1b8-be922531452d", "c38df164-ea0d-4e9e-bae6-4c3a517beb8f",
        "c79eb59b-03a4-41c9-891b-de78a8f50d5e", "c825e588-8070-4dc7-b2b4-bedaf811ffed",
        "ca43d96a-ad90-4717-a4f6-253fb26a6d53", "cb68bfe9-53a6-4345-b0e3-f6cd6c33383b",
        "cbc11b3c-0244-4fca-880f-68ebdd599894", "d001d563-988b-4f8e-904f-acb926748e22",
        "d38ee646-382d-45c0-9463-e9302aa2471a", "db98ee23-c79a-4bfb-8a50-a5ba8a69120d",
        "de291399-ead5-41dc-bc12-e7c587684f85", "dfcf6c98-1bf3-43a8-83a2-7e56b3c65d03",
        "ed036406-26a7-4c68-92d5-dcd04f62556d", "f133524e-50e2-4238-91db-393770680c9b",
        "f59f25a2-d3da-4100-a918-901271a99925", "fdbc28d8-0b83-455c-b25c-13d2a222365a",
    ]
    assert len(ids) == 106
    assert len(set(ids)) == 106
    encoded = json.dumps(sorted(ids), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    assert digest == "470c8e49e083ca29c7df4d075175b62fb5dd69311b67ca48fec6baf76cd6e892"
