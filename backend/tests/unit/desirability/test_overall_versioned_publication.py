from backend.desirability.overall_versioned_publication import OverallAuthority, project_active, rank_and_tier, validate_generation


def authority(version="overall_test_v99"):
    return OverallAuthority(version,"run","rank-gen","page-gen","2026-09-11","formula","cohort")


def test_future_v99_needs_no_schema_or_projector_change():
    rows=rank_and_tier([{"sealed_product_id":"b","score":40,"component_lineage":{"collectorVersion":"arbitrary_v44"}},{"sealed_product_id":"a","score":80,"component_lineage":{"financialVersion":"arbitrary_v55"}}])
    validate_generation(authority(),rows)
    assert [(x["rank"],x["tier"]) for x in rows]==[(2,"C"),(1,"A")]
    assert project_active(authority(),rows[0])["version"]=="overall_test_v99"


def test_unsupported_rows_never_get_fake_rank_or_tier():
    row=rank_and_tier([{"sealed_product_id":"x","score":None}])[0]
    assert row["rank"] is None and row["tier"] is None and row["eligibility_state"]=="unavailable_missing_input"


def test_projector_binds_all_authority_ids():
    row=rank_and_tier([{"sealed_product_id":"x","score":90,"component_lineage":{}}])[0]
    out=project_active(authority("v13"),row)
    assert (out["version"],out["publicationRunId"],out["rankingsGenerationId"],out["setPageGenerationId"])==("v13","run","rank-gen","page-gen")
