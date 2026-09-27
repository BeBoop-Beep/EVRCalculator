from types import SimpleNamespace
from datetime import date,timedelta
import pytest
from backend.db.services.pokemon_edition_history import (
    EditionHistoryIncomplete,read_edition_history_batch,refresh_edition_history_for_markets,
)

class Query:
    def __init__(self, client): self.client=client; self.start=0; self.end=0; self.orders=[]
    def order(self,k): self.orders.append(k); return self
    def range(self,a,b): self.start=a; self.end=b; return self
    def execute(self):
        c=self.client; c.calls.append((self.start,self.end,self.orders))
        rows=c.rows[self.start:min(self.end+1,self.start+c.cap)]
        count=len(c.rows)
        if c.mode=='missing_count':count=None
        if c.mode=='changed_count' and self.start:count+=1
        if c.mode=='empty_early' and self.start:rows=[]
        if c.mode=='repeat' and self.start:rows=c.rows[:len(rows)]
        return SimpleNamespace(data=rows,count=count)
class Client:
    def __init__(self,rows,cap=1000,mode=None):self.rows=rows;self.cap=cap;self.mode=mode;self.calls=[]
    def rpc(self,name,params,**kwargs):
        assert kwargs=={'count':'exact'}
        return Query(self)

def data():
    rows=[]
    for root,scopes in [('a',['first_edition','shadowless','unlimited']),('b',['first_edition','unlimited']),('c',['first_edition','unlimited']),('d',['first_edition','unlimited'])]:
        for scope in scopes:
            for i in range(162):
                rows.append({'set_id':root,'market_scope':scope,'market_date':(date(2026,4,16)+timedelta(days=i)).isoformat(),'certified_on_date':True,'set_value':i+1})
    return sorted(rows,key=lambda x:(x['set_id'],x['market_scope'],x['market_date']))

def read(c,**kwargs):
    return read_edition_history_batch(c,['a','b','c','d'],start_date='1999-01-01',end_date='2026-09-25',**kwargs)

def test_all_1458_rows_survive_api_cap():
    c=Client(data())
    actual=read(c)
    assert len(actual)==1458 and actual==data()
    assert actual[-1]['set_id']=='d' and actual[-1]['market_date']=='2026-09-24'
    assert len(c.calls)==6
    assert all(call[2]==['set_id','market_scope','market_date'] for call in c.calls)

def test_server_cap_below_requested_page_does_not_signal_end():
    c=Client(data(),cap=73)
    assert read(c)==data()
    assert c.calls[1][0]==73

@pytest.mark.parametrize('mode',['missing_count','changed_count','empty_early','repeat'])
def test_incomplete_or_inconsistent_response_fails_closed(mode):
    with pytest.raises(EditionHistoryIncomplete):read(Client(data(),mode=mode))

def test_zero_rows_valid():assert read(Client([]))==[]
def test_empty_root_list_no_query():assert read_edition_history_batch(None,[],start_date='2026-09-25',end_date='2026-09-25')==[]
def test_bad_scope_rejected():
    rows=[{'set_id':'a','market_scope':'blended','market_date':'2026-09-24'}]
    with pytest.raises(EditionHistoryIncomplete):read(Client(rows))
def test_wrong_date_rejected():
    rows=[{'set_id':'a','market_scope':'unlimited','market_date':'2026-09-26'}]
    with pytest.raises(EditionHistoryIncomplete):read(Client(rows))
def test_oversized_request_refused():
    with pytest.raises(ValueError):read(Client([]),page_size=1001)

def test_refresh_one_call_per_root_never_standard():
    calls=[]
    class C:
        def rpc(self,name,args):
            calls.append(args)
            result={'status':'complete','root_set_id':args['p_root_set_id'],'market_date':args['p_market_date'],'raw_v2_equal':True}
            return SimpleNamespace(execute=lambda:SimpleNamespace(data=result))
    markets=[{'id':'a','market_scope':'first_edition'},{'id':'a','market_scope':'unlimited'},{'id':'b','market_scope':'standard'}]
    assert len(refresh_edition_history_for_markets(C(),markets,market_date='2026-09-25'))==1
    assert calls==[{'p_root_set_id':'a','p_market_date':'2026-09-25'}]

@pytest.mark.parametrize('change',[{'status':'blocked'},{'market_date':'2026-09-24'},{'root_set_id':'wrong'},{'raw_v2_equal':False}])
def test_refresh_never_accepts_unverified_receipt(change):
    class C:
        def rpc(self,name,args):
            result={'status':'complete','root_set_id':'a','market_date':'2026-09-25','raw_v2_equal':True,**change}
            return SimpleNamespace(execute=lambda:SimpleNamespace(data=result))
    with pytest.raises(EditionHistoryIncomplete):
        refresh_edition_history_for_markets(C(),[{'id':'a','market_scope':'unlimited'}],market_date='2026-09-25')
