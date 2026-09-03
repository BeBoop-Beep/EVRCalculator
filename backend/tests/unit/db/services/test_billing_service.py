from dataclasses import replace
import pytest
from backend.db.services.billing_service import BillingService
from backend.domain.billing.catalog import CommercialOffer, BillingOfferNotConfigured
from backend.domain.billing.errors import BillingProviderError, BillingSubscriptionAlreadyManaged

class Repo:
    def __init__(self): self.customer=None; self.rows=[]; self.claims={}; self.recomputed=[]
    def find_customer(self, uid, provider="stripe"): return self.customer
    def create_customer_mapping(self, user_id, provider_customer_id, provider="stripe"):
        self.customer={"id":"bc_1","user_id":user_id,"provider_customer_id":provider_customer_id}; return self.customer
    def get_profile(self, uid): return {"id":uid,"email":"safe@example.com"}
    def find_customer_by_provider_id(self, cid, provider="stripe"): return self.customer if self.customer and self.customer["provider_customer_id"]==cid else None
    def upsert_subscription(self, row):
        self.rows=[r for r in self.rows if r["provider_subscription_id"]!=row["provider_subscription_id"]]+[row]; return row
    def recompute_effective_plan(self, uid): self.recomputed.append(uid); return next((r["plan"] for r in self.rows if r.get("plan")), None)
    def find_subscriptions(self, uid): return self.rows
    def manual_plan(self, uid): return None
    def claim_webhook_event(self, event_id, event_type):
        if self.claims.get(event_id)=="processed": return "duplicate"
        self.claims[event_id]="processing"; return "claimed"
    def finish_webhook_event(self, eid): self.claims[eid]="processed"
    def fail_webhook_event(self, eid, code, summary): self.claims[eid]="failed"

class Provider:
    def __init__(self): self.subscriptions={}; self.customer_calls=0; self.checkout=None; self.portal=None
    def create_customer(self, **kwargs): self.customer_calls+=1; return {"id":"cus_1"}
    def create_checkout_session(self, **kwargs): self.checkout=kwargs; return {"url":"https://checkout.stripe.test/session"}
    def retrieve_subscription(self, sid, expand=None): return self.subscriptions[sid]
    def create_customer_portal_session(self, **kwargs): self.portal=kwargs; return {"url":"https://billing.stripe.test/session"}

OFFERS={"plus_monthly":CommercialOffer("plus_monthly","plus","month",True,"price_plus",999,"usd"),
        "premium_monthly":CommercialOffer("premium_monthly","premium","month",True,"price_premium",2499,"usd")}
def sub(price="price_plus", status="active", sid="sub_1", items=1, *, cancel_at_period_end=False, cancel_at=None, current_period_end=None):
    item_rows=[]
    for _ in range(items):
        item={"price":{"id":price,"product":"prod_1"}}
        if current_period_end is not None: item["current_period_end"]=current_period_end
        item_rows.append(item)
    return {"id":sid,"customer":"cus_1","status":status,"cancel_at_period_end":cancel_at_period_end,
      "cancel_at":cancel_at,"items":{"data":item_rows}}

def service():
    repo, provider=Repo(),Provider(); repo.customer={"id":"bc_1","user_id":"u1","provider_customer_id":"cus_1"}
    return BillingService(repo,provider,OFFERS),repo,provider

def test_unconfigured_offer_never_calls_provider():
    svc,_,provider=service(); svc.offers={"x":CommercialOffer("x","plus","month")}
    with pytest.raises(BillingOfferNotConfigured): svc.create_checkout(user_id="u1",offer_key="x",success_url="a",cancel_url="b")
    assert provider.checkout is None

def test_checkout_uses_only_server_offer_customer_and_urls():
    svc,_,provider=service(); url=svc.create_checkout(user_id="u1",offer_key="plus_monthly",success_url="https://index/s",cancel_url="https://index/c")
    assert url.startswith("https://checkout.stripe.test/")
    assert provider.checkout["price_id"]=="price_plus" and provider.checkout["customer_id"]=="cus_1"

@pytest.mark.parametrize("status", ["trialing", "active", "past_due"])
def test_existing_provisionable_subscription_blocks_checkout_server_side(status):
    svc,repo,provider=service(); repo.rows=[{"provider_subscription_id":"sub_existing","status":status,"plan":"plus"}]
    with pytest.raises(BillingSubscriptionAlreadyManaged):
        svc.create_checkout(user_id="u1",offer_key="premium_monthly",success_url="a",cancel_url="b")
    assert provider.checkout is None

def test_provider_outage_never_grants_entitlement():
    svc,repo,provider=service()
    provider.create_checkout_session=lambda **kwargs: (_ for _ in ()).throw(BillingProviderError())
    with pytest.raises(BillingProviderError): svc.create_checkout(user_id="u1",offer_key="plus_monthly",success_url="a",cancel_url="b")
    assert repo.recomputed==[]

def test_orphan_customer_retry_uses_stable_provider_idempotency_key():
    repo=Repo(); provider=Provider(); svc=BillingService(repo,provider,OFFERS)
    attempts=[]
    provider.create_customer=lambda **kwargs: attempts.append(kwargs["idempotency_key"]) or {"id":"cus_stable"}
    original=repo.create_customer_mapping
    failures={"remaining":1}
    def persist(**kwargs):
        if failures["remaining"]: failures["remaining"]-=1; raise RuntimeError("db unavailable")
        return original(**kwargs)
    repo.create_customer_mapping=persist
    with pytest.raises(RuntimeError): svc.ensure_customer(user_id="u1",email="safe@example.com")
    assert svc.ensure_customer(user_id="u1",email="safe@example.com")["provider_customer_id"]=="cus_stable"
    assert attempts==["index-customer:u1","index-customer:u1"]

def test_portal_uses_persisted_customer_and_server_return_url_only():
    svc,_,provider=service(); url=svc.create_customer_portal(user_id="u1",return_url="https://index.test/account-settings?section=billing")
    assert url=="https://billing.stripe.test/session"
    assert provider.portal=={"customer_id":"cus_1","return_url":"https://index.test/account-settings?section=billing"}

def test_status_dto_distinguishes_effective_manual_and_billing_plan():
    svc,repo,_=service(); repo.rows=[{"plan":"plus","status":"active","offer_key":"plus_monthly","commercial_mapping_status":"mapped","cancel_at_period_end":False}]
    repo.manual_plan=lambda uid:"premium"
    dto=svc.billing_status("u1")
    assert dto["effectivePlan"]=="premium" and dto["billingPlan"]=="plus" and dto["accessManagedByIndex"] is True
    assert dto["billingManaged"] is True and dto["purchasableOfferKeys"]==["plus_monthly","premium_monthly"]
    assert dto["offers"]==[
        {"offerKey":"plus_monthly","plan":"plus","billingInterval":"month","unitAmount":999,"currency":"usd","purchasable":True},
        {"offerKey":"premium_monthly","plan":"premium","billingInterval":"month","unitAmount":2499,"currency":"usd","purchasable":True},
    ]

def test_public_catalog_exposes_display_data_without_provider_ids_when_checkout_is_off():
    disabled={"plus_monthly":replace(OFFERS["plus_monthly"],enabled=False)}
    dto=BillingService(Repo(),Provider(),disabled).public_catalog()
    assert dto=={"offers":[{"offerKey":"plus_monthly","plan":"plus","billingInterval":"month","unitAmount":999,"currency":"usd","purchasable":False}],"billingConfigured":False}
    assert "provider_price_id" not in str(dto)

@pytest.mark.parametrize("status",["trialing","active","past_due","incomplete","incomplete_expired","unpaid","canceled","paused","new_status"])
def test_reconciliation_persists_current_authoritative_status(status):
    svc,repo,provider=service(); provider.subscriptions["sub_1"]=sub(status=status)
    row=svc.reconcile_subscription("sub_1"); assert row["status"]==status and repo.recomputed==["u1"]

def test_managed_payments_cancel_at_period_end_shape_normalizes_to_scheduled_end():
    svc,repo,provider=service(); period_end=2_000_000_000
    provider.subscriptions["sub_1"]=sub(cancel_at_period_end=False,cancel_at=period_end,current_period_end=period_end)
    row=svc.reconcile_subscription("sub_1")
    assert row["status"]=="active"
    assert row["cancel_at_period_end"] is True
    assert svc.billing_status("u1")["cancelAtPeriodEnd"] is True

def test_billing_status_enriches_stale_local_cancellation_from_live_stripe_without_changing_entitlement():
    svc,repo,provider=service(); period_end=2_000_000_000
    repo.rows=[{"provider_subscription_id":"sub_1","plan":"plus","status":"active","offer_key":"plus_monthly",
        "commercial_mapping_status":"mapped","cancel_at_period_end":False,"current_period_end":"2099-01-01T00:00:00+00:00"}]
    provider.subscriptions["sub_1"]=sub(cancel_at_period_end=False,cancel_at=period_end,current_period_end=period_end)
    dto=svc.billing_status("u1")
    assert dto["effectivePlan"]=="plus"
    assert dto["subscriptionStatus"]=="active"
    assert dto["cancelAtPeriodEnd"] is True
    assert dto["currentPeriodEnd"]!="2099-01-01T00:00:00+00:00"

def test_arbitrary_cancel_at_does_not_masquerade_as_period_end_cancellation():
    svc,repo,provider=service(); period_end=2_000_000_000
    provider.subscriptions["sub_1"]=sub(cancel_at_period_end=False,cancel_at=period_end-3600,current_period_end=period_end)
    row=svc.reconcile_subscription("sub_1")
    assert row["cancel_at_period_end"] is False

def test_unknown_price_and_multi_item_fail_closed_but_are_audited():
    svc,repo,provider=service(); provider.subscriptions["sub_1"]=sub(price="price_unknown")
    assert svc.reconcile_subscription("sub_1")["commercial_mapping_status"]=="unmapped_price"
    provider.subscriptions["sub_2"]=sub(sid="sub_2",items=2)
    assert svc.reconcile_subscription("sub_2")["commercial_mapping_status"]=="unsupported_shape"

def test_shared_stripe_product_never_overrides_price_id_plan_authority():
    svc,repo,provider=service(); provider.subscriptions["sub_1"]=sub(price="price_premium")
    row=svc.reconcile_subscription("sub_1")
    assert row["provider_product_id"]=="prod_1"
    assert row["offer_key"]=="premium_monthly" and row["plan"]=="premium"

def test_duplicate_event_is_safe_and_failed_event_can_retry():
    svc,repo,provider=service(); provider.subscriptions["sub_1"]=sub()
    event={"id":"evt_1","type":"customer.subscription.updated","data":{"object":{"id":"sub_1"}}}
    assert svc.handle_event(event)=="processed"; assert svc.handle_event(event)=="duplicate"; assert len(repo.rows)==1

def test_event_order_retrieves_current_state_and_cannot_resurrect_deleted():
    svc,repo,provider=service(); provider.subscriptions["sub_1"]=sub(status="canceled")
    older={"id":"evt_old","type":"customer.subscription.updated","data":{"object":{"id":"sub_1","status":"active"}}}
    svc.handle_event(older); assert repo.rows[0]["status"]=="canceled"

def test_dahlia_invoice_parent_subscription_reference_reconciles():
    svc,repo,provider=service(); provider.subscriptions["sub_1"]=sub()
    event={"id":"evt_invoice","type":"invoice.paid","data":{"object":{"parent":{"subscription_details":{"subscription":"sub_1"}}}}}
    assert svc.handle_event(event)=="processed" and repo.rows[0]["provider_subscription_id"]=="sub_1"
