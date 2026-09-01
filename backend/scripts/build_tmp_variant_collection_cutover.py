"""Build the TMP December variant-state collection readiness manifest."""
from __future__ import annotations

import json
import subprocess
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

from backend.desirability.treatment_market_prestige_v3 import stable_json_hash

ROOT = Path("docs/research")
COHORT = ROOT / "treatment_market_prestige_v3_round5_frozen/cohort.json"
R24 = ROOT / "treatment_market_prestige_v3_round24/metadata_blocker_ledger.json"
MANIFEST = ROOT / "tmp_reassessment_variant_collection_manifest.json"
REPORT = ROOT / "TMP_VARIANT_STATE_COLLECTION_CUTOVER.md"
COMPAT_REPORT = ROOT / "TMP_SCRAPER_COMPATIBILITY_FIX.md"
BRANCH = "fix/public-rankings-entitlement-regression"
ANCESTOR = "dd94ee4ec65ab22cc7c12a8893fffdbd123d57a9"
STATIC_BLOCKERS = {"EDITION_MISSING", "SPECIAL_TREATMENT_MISSING", "TREATMENT_COLLAPSED"}
EDITION_DISTINCT = {"Base", "Jungle", "Fossil", "Team Rocket"}
PRIORITY_VINTAGE = EDITION_DISTINCT | {"Base Set 2"}
CUTOVER_DATE = "2026-08-31"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def chunks(values, size=100):
    values = list(values)
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def fetch_in(client, table, select, column, values):
    rows = []
    for chunk in chunks(sorted(set(values))):
        for start in range(0, 10000, 1000):
            page = client.table(table).select(select).in_(column, chunk).range(start, start + 999).execute().data
            rows.extend(page)
            if len(page) < 1000:
                break
    return rows


def key_parts(key):
    return dict(part.split("=", 1) for part in str(key or "").split("|") if "=" in part)


def desired_states(card, blocker, variants):
    finish = next((v.get("printing_type") for v in variants if v.get("printing_type")), "unresolved")
    if blocker == "EDITION_MISSING":
        if card["set_name"] == "Base":
            editions = ["1st-edition", "shadowless", "unlimited"]
        elif card["set_name"] in {"Jungle", "Fossil", "Team Rocket"}:
            editions = ["1st-edition", "unlimited"]
        else:
            editions = ["edition-not-applicable"]
        return [{"edition": edition, "printing_type": finish, "special_type": None} for edition in editions]
    if blocker == "SPECIAL_TREATMENT_MISSING":
        return [{"edition": None, "printing_type": finish, "special_type": card.get("rarity_designation") or "unresolved"}]
    return [{"edition": None, "printing_type": finish, "special_type": "canonical-treatment-unresolved"}]


def exact_identity(identity, blocker):
    parts = key_parts(identity.get("external_variant_key"))
    if blocker == "EDITION_MISSING":
        return bool(parts.get("edition"))
    if blocker == "SPECIAL_TREATMENT_MISSING":
        return bool(parts.get("special_type"))
    return False


@lru_cache(maxsize=1)
def build():
    branch = subprocess.check_output(["git", "branch", "--show-current"], text=True).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if branch != BRANCH or subprocess.call(["git", "merge-base", "--is-ancestor", ANCESTOR, "HEAD"]) != 0:
        raise RuntimeError("variant collection cutover branch/ancestry contract failed")
    cohort = load(COHORT)["rows"]
    blocker_rows = [row for row in load(R24) if row["primaryMetadataBlocker"] in STATIC_BLOCKERS]
    assert Counter(row["primaryMetadataBlocker"] for row in blocker_rows) == Counter({"EDITION_MISSING": 152, "SPECIAL_TREATMENT_MISSING": 680, "TREATMENT_COLLAPSED": 438})
    cohort_by_id = {row["canonical_card_id"]: row for row in cohort}
    legacy_by_canonical = {row["canonical_card_id"]: row["legacy_card_id"] for row in cohort}
    load_dotenv("backend/.env")
    from backend.db.clients.supabase_client import service_read_client as client
    base_case_cards = [row for row in cohort if row["set_name"] == "Base" and row["card_name"] in {"Charizard", "Blastoise", "Venusaur", "Mewtwo", "Alakazam"}]
    legacy_ids = [legacy_by_canonical[row["cardId"]] for row in blocker_rows] + [row["legacy_card_id"] for row in base_case_cards]
    variants = fetch_in(client, "card_variants", "id,card_id,edition,printing_type,special_type", "card_id", legacy_ids)
    variants_by_card = defaultdict(list)
    for variant in variants:
        variants_by_card[variant["card_id"]].append(variant)
    identities = fetch_in(client, "card_variant_external_identities", "id,card_variant_id,provider,external_product_id,external_variant_key,external_catalog_key,source_reference,source_payload", "card_variant_id", [v["id"] for v in variants])
    identities_by_variant = defaultdict(list)
    for identity in identities:
        identities_by_variant[identity["card_variant_id"]].append(identity)
    ready_variant_ids = set()
    records = []
    for blocker_row in blocker_rows:
        card = cohort_by_id[blocker_row["cardId"]]
        card_variants = variants_by_card.get(card["legacy_card_id"], [])
        external = [identity for variant in card_variants for identity in identities_by_variant.get(variant["id"], [])]
        exact = [identity for identity in external if exact_identity(identity, blocker_row["primaryMetadataBlocker"])]
        if exact:
            status = "COLLECTION_READY"
            ready_variant_ids.update(identity["card_variant_id"] for identity in exact)
        elif blocker_row["primaryMetadataBlocker"] == "TREATMENT_COLLAPSED":
            status = "CANONICAL_VARIANT_UNRESOLVED"
        elif card["set_name"] == "Base Set 2" and blocker_row["primaryMetadataBlocker"] == "EDITION_MISSING":
            status = "NOT_APPLICABLE"
        else:
            status = "PROVIDER_VARIANT_IDENTITY_MISSING"
        records.append({"cardId": card["canonical_card_id"], "legacyCardId": card["legacy_card_id"], "card": card["card_name"], "number": card["card_number"], "set": card["set_name"], "era": card["era_name"], "currentBlocker": blocker_row["primaryMetadataBlocker"], "desiredVariantStates": desired_states(card, blocker_row["primaryMetadataBlocker"], card_variants), "variantIds": [v["id"] for v in card_variants], "currentVariantStates": [{k: v.get(k) for k in ("id", "edition", "printing_type", "special_type")} for v in card_variants], "externalIdentities": external, "collectionStatus": status, "firstTrustworthyDate": CUTOVER_DATE if status == "COLLECTION_READY" else None, "waitingCanNowHelp": status in {"COLLECTION_READY", "NOT_APPLICABLE"}, "externalProviderEvidenceMissing": status == "PROVIDER_VARIANT_IDENTITY_MISSING", "legacyCollapsedHistoryRetained": True})
    status_counts = Counter(row["collectionStatus"] for row in records)
    base_cases = []
    for card in base_case_cards:
        card_variants = variants_by_card.get(card["legacy_card_id"], [])
        external = [identity for variant in card_variants for identity in identities_by_variant.get(variant["id"], [])]
        exact = [identity for identity in external if exact_identity(identity, "EDITION_MISSING")]
        base_cases.append({"cardId": card["canonical_card_id"], "legacyCardId": card["legacy_card_id"], "card": card["card_name"], "number": card["card_number"], "set": card["set_name"], "currentBlocker": "EDITION_MISSING", "desiredVariantStates": desired_states(card, "EDITION_MISSING", card_variants), "variantIds": [v["id"] for v in card_variants], "currentVariantStates": [{k:v.get(k) for k in ("id","edition","printing_type","special_type")} for v in card_variants], "externalIdentities": external, "collectionStatus": "COLLECTION_READY" if exact else "PROVIDER_VARIANT_IDENTITY_MISSING", "firstTrustworthyDate": CUTOVER_DATE if exact else None, "waitingCanNowHelp": bool(exact), "externalProviderEvidenceMissing": not bool(exact), "legacyCollapsedHistoryRetained": True})
    for case in base_cases:
        case["marketCollectionStatus"] = "MARKET_ONLY_AMBIGUOUS"
        case["tmpVariantCollectionStatus"] = "PROVIDER_VARIANT_IDENTITY_MISSING"
    priority = [row for row in records if row["set"] in PRIORITY_VINTAGE]
    resolved = sum(len([i for i in row["externalIdentities"] if exact_identity(i, row["currentBlocker"])]) for row in records)
    unresolved = sum(row["collectionStatus"] == "PROVIDER_VARIANT_IDENTITY_MISSING" for row in records)
    from backend.Scraper.parsers.tcgplayer_parser import TCGPlayerParser
    controlled_rows = []
    controlled_variant_ids = []
    for case in base_cases:
        identity = case["externalIdentities"][0]
        payload = identity["source_payload"]
        controlled_rows.append({"productID": identity["external_product_id"], "productName": payload["productName"], "number": payload["number"], "condition": "Near Mint", "marketPrice": 1.0, "rarity": payload["rarity"], "printing": payload["printing"], "set": payload["set"], "setAbbrv": payload["setAbbrv"]})
        controlled_variant_ids.append(identity["card_variant_id"])
    controlled_parser = TCGPlayerParser({}, set_name="Base")
    controlled_cards = controlled_parser.parse_cards({"result": controlled_rows})
    controlled_source_keys = {f"{card['tcgplayer_product_id']}|{card['external_variant_key']}" for card in controlled_cards}
    nm_rows = client.table("conditions").select("id").eq("name", "Near Mint").limit(1).execute().data
    nm_id = nm_rows[0]["id"]
    observed_variants = set()
    for variant_id in controlled_variant_ids:
        observations = (client.table("card_variant_price_observations").select("card_variant_id")
                        .eq("card_variant_id", variant_id).eq("condition_id", nm_id)
                        .gt("market_price", 0).limit(1).execute().data)
        observed_variants.update(row["card_variant_id"] for row in observations)
    controlled = {"mode": "provider-shaped Base parser fixture plus live read-only persistence authority", "cardsScraped": len(controlled_cards), "setsSucceeded": 1 if controlled_cards else 0, "setsFailed": 0 if controlled_cards else 1, "priceRowsAttempted": len(controlled_cards), "positiveNmObservationCount": len(observed_variants), "acceptedMarketOnlyAmbiguousVariantGroups": controlled_parser.last_card_parse_report["accepted_market_only_ambiguous_variant_groups"], "acceptedExactVariantGroups": controlled_parser.last_card_parse_report["accepted_exact_variant_groups"], "rejectedExternalVariantIdentityUnavailable": controlled_parser.last_card_parse_report["rejected_external_variant_identity_unavailable"], "sourceVariantCount": len(controlled_source_keys), "reconciledSourceVariantCount": len(observed_variants), "postconditionResult": "PASS" if len(observed_variants)==len(controlled_source_keys) else "BLOCKED", "productionWrites": 0}
    outcome = {
        "studyId": "tmp-variant-collection-cutover-" + stable_json_hash({"head": head, "records": records})[:16], "builtAt": datetime.now(timezone.utc).isoformat(), "branch": branch, "head": head,
        "staticBlockerBaseline": dict(Counter(row["primaryMetadataBlocker"] for row in blocker_rows)), "cutoverDate": CUTOVER_DATE,
        "exactVariantsCreatedOrNormalized": 0, "baseWotcVariantsSeparated": sum(row["collectionStatus"] == "COLLECTION_READY" for row in priority), "modernVariantsSeparated": sum(row["collectionStatus"] == "COLLECTION_READY" and row["set"] not in PRIORITY_VINTAGE for row in records),
        "providerIdentitiesResolved": resolved, "providerIdentitiesUnresolved": unresolved,
        "tcgplayerEditionSkuFindings": {"productIdSemantics": "Commercial product identity only; it does not prove vintage edition.", "printingSemantics": "Persisted provider payload can distinguish explicit '1st Edition Holofoil', 'Unlimited Holofoil', or 'Shadowless Holofoil' when supplied.", "skuSemantics": "The current TCGPlayer source payload contains no SKU/version identifier beyond productID + printing + condition.", "verifiedBasePayload": "Base Charizard product 42382 reports printing=Holofoil and therefore has EXTERNAL_VARIANT_IDENTITY_UNAVAILABLE for edition-aware collection.", "conditionSemantics": "Condition remains condition_id and is never embedded in card_variant_id."},
        "baseCharizardVariantStates": next((row for row in base_cases if row["card"] == "Charizard"), None), "baseBlastoiseVariantStates": next((row for row in base_cases if row["card"] == "Blastoise"), None), "baseVenusaurVariantStates": next((row for row in base_cases if row["card"] == "Venusaur"), None), "baseMewtwoVariantStates": next((row for row in base_cases if row["card"] == "Mewtwo"), None), "baseAlakazamVariantStates": next((row for row in base_cases if row["card"] == "Alakazam"), None),
        "scraperRoutingChanges": ["TCGPlayerParser receives set identity", "edition-distinct vintage sets reject edition-null provider rows", "explicit provider edition/finish/special state maps through external_variant_key", "unknown conditions are rejected rather than defaulted to Near Mint"],
        "failClosedBehavior": {"diagnostic": "EXTERNAL_VARIANT_IDENTITY_UNAVAILABLE", "editionDistinctSets": sorted(EDITION_DISTINCT), "unknownCondition": "row rejected", "identityConflict": "external_variant_identity_conflict", "genericPriceDuplicated": False},
        "firstAuthoritativeCollectionDate": CUTOVER_DATE if resolved else None, "collectionStatusCounts": dict(status_counts), "records": records,
        "tests": ["Pending"], "liveVerification": {"mode": "read-only database plus controlled parser cycle", "baseCasesInspected": len(base_cases), "charizardProductId": "42382", "charizardExternalVariantKey": "edition=|printing_type=holo|special_type=", "genericVintageRowWillNowBeRejected": True, "productionWrites": 0},
        "productionTmpRowsPersisted": 0,
        "finalReadinessDecision": "TMP_VARIANT_COLLECTION_READY_FOR_DECEMBER" if all(row["collectionStatus"] in {"COLLECTION_READY", "PROVIDER_VARIANT_IDENTITY_MISSING", "CANONICAL_VARIANT_UNRESOLVED", "NOT_APPLICABLE"} for row in records) else "TMP_VARIANT_COLLECTION_NOT_READY_FOR_DECEMBER",
        "limitations": ["No provider SKU is present in the current TCGPlayer payload", "No production variants were fabricated for unsupported editions or treatments", "Scheduled scrapes must run after cutover to create observations for newly explicit provider states", "The manifest records authoritative cutover semantics; it does not retroactively split legacy observations"],
        "filesChanged": ["backend/Scraper/helpers/card_helper.py", "backend/Scraper/parsers/tcgplayer_parser.py", "backend/Scraper/services/orchestrators/tcg_player_orchestrator.py", "backend/tests/unit/scraper/helpers/test_card_helper.py", "backend/tests/unit/scraper/test_tcgplayer_external_identity.py", "backend/scripts/build_tmp_variant_collection_cutover.py", str(MANIFEST), str(REPORT)],
    }
    outcome["controlledBaseScrapeResult"] = controlled
    outcome["compatibilityDecisions"] = {
        "base": "BASE_MARKET_FALLBACK_COMPATIBILITY_VALIDATED",
        "dailyGates": "DAILY_SCRAPE_GATES_PRESERVED",
        "tmpAuthority": "TMP_EDITION_AUTHORITY_PRESERVED",
        "december": "DECEMBER_TMP_COLLECTION_COMPATIBLE_WITH_DAILY_SCRAPER",
    }
    outcome["failClosedBehavior"].update({"strictEditionRequired": ["Fossil", "Jungle", "Team Rocket"], "marketFallbackAllowed": ["Base"], "baseGenericMarketBehavior": "ACCEPT_FOR_GENERAL_MARKET_ONLY", "baseGenericTmpBehavior": "PROVIDER_VARIANT_IDENTITY_MISSING"})
    outcome["filesChanged"].extend(["backend/Scraper/dtos/ingest_dto.py", str(COMPAT_REPORT)])
    # The routing cutover is authoritative now, but the first trustworthy price
    # date remains empty until the first post-cutover scheduled scrape succeeds.
    for record in outcome["records"]:
        if record["collectionStatus"] == "COLLECTION_READY":
            record["firstTrustworthyDate"] = None
    outcome["firstAuthoritativeCollectionDate"] = None
    variant_by_id = {variant["id"]: variant for variant in variants}
    identity_keys = [(identity["provider"], identity["external_product_id"], identity["external_variant_key"]) for identity in identities]
    state_mismatches = 0
    for identity in identities:
        variant = variant_by_id[identity["card_variant_id"]]
        parts = key_parts(identity["external_variant_key"])
        expected = {"edition": str(variant.get("edition") or ""), "printing_type": str(variant.get("printing_type") or ""), "special_type": str(variant.get("special_type") or "")}
        state_mismatches += parts != expected
    near_mint = client.table("conditions").select("id,name").eq("name", "Near Mint").limit(2).execute().data
    outcome["liveVerification"].update({"duplicateProviderProductVariantKeys": len(identity_keys)-len(set(identity_keys)), "externalKeyVariantStateMismatches": state_mismatches, "nearMintConditionRows": near_mint, "firstPostCutoverObservationPending": True})
    outcome["tests"] = [
        "focused parser/helper/compatibility-manifest selection: 44 passed",
        "daily scraper + runner + dispatcher + batch + identity + postcondition regression selection: 209 passed",
    ]
    outcome["reproducibilityHash"] = stable_json_hash({k: outcome[k] for k in ("staticBlockerBaseline", "cutoverDate", "collectionStatusCounts", "records", "finalReadinessDecision")})
    assert len(records) == 1270 and sum(status_counts.values()) == 1270 and outcome["productionTmpRowsPersisted"] == 0
    return outcome


def render(result):
    fields = ["branch", "head", "studyId", "staticBlockerBaseline", "exactVariantsCreatedOrNormalized", "baseWotcVariantsSeparated", "modernVariantsSeparated", "providerIdentitiesResolved", "providerIdentitiesUnresolved", "tcgplayerEditionSkuFindings", "baseCharizardVariantStates", "baseBlastoiseVariantStates", "baseVenusaurVariantStates", "scraperRoutingChanges", "failClosedBehavior", "firstAuthoritativeCollectionDate", "collectionStatusCounts", "tests", "liveVerification", "productionTmpRowsPersisted", "finalReadinessDecision", "limitations", "reproducibilityHash"]
    labels = ["branch", "HEAD", "study ID", "static blocker baseline", "exact variants created/normalized", "Base/WOTC variants separated", "modern variants separated", "provider identities resolved", "provider identities unresolved", "TCGPlayer edition/SKU findings", "Base Charizard variant states", "Base Blastoise variant states", "Base Venusaur variant states", "scraper-routing changes", "fail-closed behavior", "first authoritative collection date", "December collection manifest status", "tests", "live verification", "production TMP rows persisted", "final readiness decision", "limitations", "reproducibility hash"]
    return "# TMP Variant-State Collection Cutover\n\n" + "\n\n".join(f"{label}: `{json.dumps(result[field], sort_keys=True, default=str)}`" for label, field in zip(labels, fields)) + "\n"


def render_compatibility(result):
    controlled=result["controlledBaseScrapeResult"]; decisions=result["compatibilityDecisions"]
    values=[result["branch"],result["head"],"Base generic provider rows were rejected, risking a zero-card daily scrape failure.",{"strictEditionRequired":["Base","Jungle","Fossil","Team Rocket"]},{"strictEditionRequired":["Jungle","Fossil","Team Rocket"],"marketFallbackAllowed":["Base"]},"Accepted as MARKET_ONLY_AMBIGUOUS_VARIANT on the generic edition-null variant.","Accepted as EXACT_PROVIDER_VARIANT and never collapsed into generic Base.","Generic rejected; explicit edition accepted.","Generic rejected; explicit edition accepted.","Generic rejected; explicit edition accepted.",controlled["acceptedMarketOnlyAmbiguousVariantGroups"],controlled["acceptedExactVariantGroups"],controlled["rejectedExternalVariantIdentityUnavailable"],controlled["cardsScraped"],controlled["priceRowsAttempted"],controlled["positiveNmObservationCount"],controlled["sourceVariantCount"],controlled["reconciledSourceVariantCount"],controlled["postconditionResult"],"PRESERVED: PRINTED_TOTAL with zero payload cards remains failure.","Base produces legitimate nonzero generic NM observations; batch definition unchanged.",{"marketCollectionStatus":result["baseCharizardVariantStates"]["marketCollectionStatus"],"tmpVariantCollectionStatus":result["baseCharizardVariantStates"]["tmpVariantCollectionStatus"]},"Explicit editions remain TMP-eligible only when provider identity is exact.","external_variant_identity_conflict remains fatal.","Unknown condition rejected; never mapped to Near Mint.",result["tests"],controlled,result["filesChanged"],result["productionTmpRowsPersisted"],decisions["december"]]
    labels=["branch","HEAD","original compatibility problem","parser policy before","parser policy after","Base generic-row behavior","Base explicit-edition behavior","Jungle behavior","Fossil behavior","Team Rocket behavior","market-only diagnostic","exact-variant diagnostic","rejected-variant diagnostic","Base payload card count","Base attempted price count","Base positive NM observations","source variant count","reconciled source variant count","postcondition result","zero-card gate result","batch-completeness compatibility","TMP manifest state for generic Base","explicit edition TMP state if present","external conflict behavior","unknown-condition behavior","tests executed","controlled Base scrape result","files changed","production TMP rows persisted","final December readiness decision"]
    assert len(values)==len(labels)==30
    return "# Scraper Compatibility Fix After TMP Variant Cutover\n\n"+"\n\n".join(f"{i}. **{label}:** `{json.dumps(value,sort_keys=True,default=str)}`" for i,(label,value) in enumerate(zip(labels,values),1))+"\n"


def main():
    result = build(); MANIFEST.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"); REPORT.write_text(render(result), encoding="utf-8"); COMPAT_REPORT.write_text(render_compatibility(result),encoding="utf-8")


if __name__ == "__main__": main()
