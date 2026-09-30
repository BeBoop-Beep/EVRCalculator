from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[5]
SPEC = importlib.util.spec_from_file_location("market_activity_v1_under_test", ROOT / "backend/db/services/market_activity_v1.py")
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)
read_constituent_activity_page = MODULE.read_constituent_activity_page
read_group_activity = MODULE.read_group_activity
read_instrument_activity = MODULE.read_instrument_activity
DETAIL = json.loads((ROOT / "docs/research/market_activity_v1/fixtures/fma_fixture_12_legacy_no_receipts.json").read_text())["expected"]
GROUP = json.loads((ROOT / "docs/research/market_activity_v1/fixtures/fma_fixture_11_group_activity.json").read_text())["expected"]
GEN = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SURFACE = "11111111-1111-4111-8111-111111111111"
REF = {"kind":"SURFACE_V2_GENERATION","generationId":SURFACE,"marketKey":"quick:core"}


class Result:
    def __init__(self,data): self.data=data


class Query:
    def __init__(self, client, table): self.client=client; self.table=table; self.filters={}; self.args={}
    def select(self,*_): return self
    def eq(self,key,value): self.filters[key]=value; return self
    def limit(self,*_): return self
    def order(self,*_,**__): return self
    def range(self,*_): return self
    def execute(self):
        self.client.query_count += 1
        if self.table == "market_activity_generations_v1":
            return Result([{"activity_generation_id":GEN,"state":"VALIDATED","serving_state":"RETAINED",
                            "evidence_cutoff":"2026-09-30T12:00:00Z","validated_at":"2026-09-30T12:01:00Z",
                            "policy":DETAIL["policy"]}])
        if self.table == "market_activity_rosters_v1":
            return Result([{"activity_generation_id":GEN,"market_key":self.filters.get("market_key"),"roster_revision":self.client.roster_ref,
                            "roster_as_of":"2026-09-29","roster_denominator":self.client.denominator}])
        if self.table == "market_activity_group_payloads_v1":
            return Result([{"payload": GROUP}])
        if self.table == "market_activity_instrument_payloads_v1":
            return Result([{"payload": DETAIL}])
        raise AssertionError(f"unexpected table query {self.table}")


class RpcQuery:
    def __init__(self,client,args): self.client=client; self.args=args
    def execute(self):
        self.client.query_count += 1
        start=self.args["p_after_rank"]+1; stop=min(self.client.denominator,start+self.args["p_limit"]-1)
        return Result([{"rank":rank,"instrument_key":DETAIL["request"]["instrumentKey"],
                        "card_variant_id":DETAIL["instrument"]["cardVariantId"],"payload":DETAIL}
                       for rank in range(start,stop+1)])


class Client:
    def __init__(self,denominator,roster_ref=REF): self.denominator=denominator; self.roster_ref=roster_ref; self.query_count=0
    def table(self,name): return Query(self,name)
    def rpc(self,name,args):
        assert name=="get_market_activity_constituent_page_v1"
        return RpcQuery(self,args)


@pytest.mark.parametrize("denominator",[100,207,990])
def test_page_query_count_is_constant_not_roster_sized(denominator):
    client=Client(denominator)
    response=read_constituent_activity_page(client,{"marketKey":"quick:core","activityGenerationId":GEN,
        "rosterRef":REF,"asOf":"2026-09-29","windowDays":30,"cursor":None,"limit":50})
    assert response["availability"]["state"]=="AVAILABLE"
    assert len(response["rows"])==50
    assert response["page"]["totalCount"]==denominator
    assert client.query_count==3


def test_group_and_instrument_reads_each_use_three_calls():
    group_client = Client(3, GROUP["request"]["rosterRef"])
    group = read_group_activity(group_client, GROUP["request"])
    assert group["kind"] == "groupActivity"
    assert group_client.query_count == 3
    instrument_client = Client(3, DETAIL["request"]["rosterRef"])
    detail = read_instrument_activity(instrument_client, DETAIL["request"])
    assert detail["kind"] == "instrumentDetail"
    assert instrument_client.query_count == 3
