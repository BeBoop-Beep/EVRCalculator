from backend.scripts.build_treatment_market_prestige_v3_round21 import GATES, REPETITIONS, build


def test_round21_freezes_only_identified_structural_candidates():
    study=build(); population=study["_candidate"]
    assert study["frozenCandidateCards"]==2043==len(population)
    assert len({x["cardId"] for x in population})==2043
    assert all(x["priorProvenance"]=="UNRESOLVED" for x in population)
    assert not any(x["recoveryClass"] in {"HISTORY_MISSING","MODEL_INSTABILITY","CANONICAL_MAPPING"} for x in population)


def test_round21_runs_repeated_pseudo_sparsity_with_preregistered_gates():
    study=build()
    assert study["pseudoSparsityRepetitionCount"]==REPETITIONS==200
    assert study["preregisteredGates"]==GATES
    assert set(study["modelCandidates"])=={"STANDALONE_V3_CONTROL","HIERARCHICAL_TREATMENT","TREATMENT_FAMILY_HIERARCHICAL","CROSS_CLASSIFIED_HIERARCHICAL"}
    assert study["validation"][study["diagnosticBestModel"]]["RESIDUAL_MATCHED"]["metrics"]["n"]>0


def test_round21_all_gates_control_real_target_recovery():
    study=build()
    assert study["decisions"]["framework"]=="HIERARCHICAL_TMP_NOT_SUPPORTED"
    assert study["selectedModel"] is None
    assert study["realTargetTreatmentsAttempted"]==0
    assert study["hierarchicalEmpiricalCardsRecovered"]==0
    assert not study["_recovered"]


def test_round21_preserves_provenance_coverage_and_production_safety():
    study=build(); coverage=study["coverage"]
    assert coverage["directEmpiricalCatalog"]["cards"]==10996
    assert coverage["hierarchicalEmpiricalCatalog"]["cards"]==0
    assert coverage["combinedUsableCatalog"]["cards"]==11367
    assert study["finalSparseIdentificationStatus"]=="SPARSE_NUMERIC_TMP_CURRENTLY_UNIDENTIFIABLE"
    assert study["productionPaused"] and study["rowsPersisted"]==0
