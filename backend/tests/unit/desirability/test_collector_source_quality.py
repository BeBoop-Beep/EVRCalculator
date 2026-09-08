from backend.desirability.collector_source_quality import limitless_gate, registry_gate, trends_gate

def test_limitless_gate_is_source_specific():
    assert limitless_gate({"observations":100,"matched":99,"ambiguous":1,"eventsSelected":10,"meanDecklistCoverage":.9})["passed"]
    assert not limitless_gate({"observations":100,"matched":90,"ambiguous":10,"eventsSelected":3,"meanDecklistCoverage":1})["passed"]

def test_registry_and_trends_gates_refuse_low_coverage():
    assert not registry_gate({"namedCharacterCoverage":.5,"premiumNamedCoverage":1,"hitEligibleNamedCoverage":1})["passed"]
    assert trends_gate({"eligible":10,"scaled":9,"zeroConfirmed":1,"unresolved":0,"anchorBridgeIntegrity":True,"apparentZerosRetested":True},"trainer_trends")["passed"]

def test_artist_gate_counts_confirmed_zero_as_retrieved_not_observable():
    result=trends_gate({"eligible":60,"scaled":23,"zeroConfirmed":37,"unresolved":0,"anchorBridgeIntegrity":True,"apparentZerosRetested":True},"artist_trends")
    assert result["passed"]
    assert result["retrievalCoverage"] == 1
    assert result["observableSignalCoverage"] == 23/60
