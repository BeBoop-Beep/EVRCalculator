from backend.db.services.pokemon_card_detail_service import _load_treatment_prestige


class Result:
    def __init__(self, data): self.data=data
class Query:
    def __init__(self, rows): self.rows=rows
    def select(self,*_): return self
    def eq(self,key,value): self.rows=[r for r in self.rows if str(r.get(key))==str(value)]; return self
    def execute(self): return Result(self.rows)
class Client:
    def __init__(self, rows): self.rows=rows
    def table(self, name): assert name=="pokemon_card_treatment_scores_latest"; return Query(list(self.rows))


def test_approved_lookup_prefers_era_scope():
    rows=[{"treatment_key":"rare","scope_type":"global","era_id":None,"supertype":None,"treatment_score_100":40},
          {"treatment_key":"rare","scope_type":"era","era_id":"e1","supertype":None,"treatment_score_100":70}]
    result=_load_treatment_prestige(Client(rows),rarity="Rare",variant={},era_id="e1",supertype="Pokemon")
    assert result["available"] is True and result["score"]==70


def test_no_approved_row_never_falls_back_to_v1():
    result=_load_treatment_prestige(Client([]),rarity="Rare",variant={},era_id="e1",supertype="Pokemon")
    assert result["available"] is False
    assert "score" not in result


def test_unmapped_variant_is_unavailable_without_database_read():
    result=_load_treatment_prestige(Client([]),rarity="Unknown",variant={},era_id=None,supertype="Pokemon")
    assert result["status"]=="unmapped_treatment"
