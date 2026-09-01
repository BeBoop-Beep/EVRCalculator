from fastapi.testclient import TestClient
from backend.api import main
from backend.domain.billing.catalog import BillingOfferNotConfigured
import hashlib
import hmac
import time
from backend.domain.billing.providers.stripe_provider import StripeProvider

client=TestClient(main.app)

class FakeService:
    checkout_calls=[]; events=[]; portal_calls=[]
    def __init__(self):
        self.provider=self
    def create_checkout(self, **kwargs): self.checkout_calls.append(kwargs); return "https://checkout.stripe.test/cs_1"
    def billing_status(self, uid): return {"effectivePlan":None,"billingManaged":False,"subscriptionStatus":None,"offerKey":None,"cancelAtPeriodEnd":False,"currentPeriodEnd":None,"billingConfigured":False}
    def create_customer_portal(self, **kwargs): self.portal_calls.append(kwargs); return "https://billing.stripe.test/session"
    def construct_event(self, raw, signature):
        if signature!="valid":
            from backend.domain.billing.errors import InvalidWebhookSignature
            raise InvalidWebhookSignature()
        return {"id":"evt_1","type":"unhandled","data":{"object":{}}}
    def handle_event(self,event): self.events.append(event); return "processed"

def auth(monkeypatch): monkeypatch.setattr(main,"decode_token",lambda token: ({"id":"user-a"},None) if token=="good" else (None,({"message":"Not authenticated"},401)))

def test_anonymous_checkout_denied(monkeypatch):
    auth(monkeypatch); assert client.post("/billing/checkout-session",json={"offerKey":"plus_monthly"}).status_code==401

def test_cross_site_billing_posts_are_rejected_before_provider_calls(monkeypatch):
    auth(monkeypatch); monkeypatch.setattr(main,"BillingService",FakeService)
    headers={"Authorization":"Bearer good","Origin":"https://evil.test","Sec-Fetch-Site":"cross-site"}
    before_checkout, before_portal = len(FakeService.checkout_calls), len(FakeService.portal_calls)
    assert client.post("/billing/checkout-session",json={"offerKey":"plus_monthly"},headers=headers).status_code==403
    assert client.post("/billing/customer-portal",headers=headers).status_code==403
    assert (len(FakeService.checkout_calls),len(FakeService.portal_calls))==(before_checkout,before_portal)

def test_checkout_rejects_every_client_authority_field(monkeypatch):
    auth(monkeypatch); monkeypatch.setattr(main,"BillingService",FakeService)
    headers={"Authorization":"Bearer good"}
    for field,value in [("amount",0),("plan","premium"),("priceId","price_evil"),("user_id","other"),("customerId","cus_other"),("success_url","https://evil.test")]:
        assert client.post("/billing/checkout-session",json={"offerKey":"plus_monthly",field:value},headers=headers).status_code==422
    response=client.post("/billing/checkout-session",json={"offerKey":"plus_monthly"},headers=headers)
    assert response.status_code==200 and response.json()=={"checkoutUrl":"https://checkout.stripe.test/cs_1"}
    assert FakeService.checkout_calls[-1]["user_id"]=="user-a"

def test_billing_me_is_authenticated_safe_dto(monkeypatch):
    auth(monkeypatch); monkeypatch.setattr(main,"BillingService",FakeService)
    assert client.get("/billing/me").status_code==401
    body=client.get("/billing/me",headers={"Authorization":"Bearer good"}).json()
    assert "provider_customer_id" not in body and body["billingManaged"] is False

def test_webhook_requires_signature_and_raw_verified_event(monkeypatch):
    monkeypatch.setattr(main,"BillingService",FakeService); FakeService.events.clear()
    assert client.post("/billing/stripe/webhook",content=b'{}').status_code==400
    assert client.post("/billing/stripe/webhook",content=b'{}',headers={"Stripe-Signature":"invalid"}).status_code==400
    assert FakeService.events==[]
    assert client.post("/billing/stripe/webhook",content=b'{}',headers={"Stripe-Signature":"valid"}).status_code==200
    assert len(FakeService.events)==1

def test_portal_requires_auth_and_uses_server_owned_identity_and_return(monkeypatch):
    auth(monkeypatch); monkeypatch.setattr(main,"BillingService",FakeService); FakeService.portal_calls.clear()
    assert client.post("/billing/customer-portal").status_code==401
    response=client.post("/billing/customer-portal",json={"customerId":"cus_other","returnUrl":"https://evil.test"},headers={"Authorization":"Bearer good"})
    assert response.status_code==200 and response.json()=={"portalUrl":"https://billing.stripe.test/session"}
    assert FakeService.portal_calls==[{"user_id":"user-a","return_url":"http://localhost:3000/account-settings?section=billing"}]

def test_framework_boundary_preserves_exact_raw_body_for_stripe_signature(monkeypatch):
    secret = "whsec_boundary_test"
    accepted = []
    class BoundaryService:
        provider = StripeProvider(secret_key="", webhook_secret=secret)
        def handle_event(self, event): accepted.append(event); return "processed"
    monkeypatch.setattr(main, "BillingService", BoundaryService)
    payload = b'{"id":"evt_raw","object":"event","type":"unhandled","data":{"object":{}}}'
    timestamp = int(time.time())
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    signature = f"t={timestamp},v1={digest}"
    assert client.post("/billing/stripe/webhook", content=payload, headers={"Stripe-Signature":signature}).status_code == 200
    assert len(accepted) == 1
    assert client.post("/billing/stripe/webhook", content=payload+b" ", headers={"Stripe-Signature":signature}).status_code == 400
    assert client.post("/billing/stripe/webhook", content=b'{"object":"event","type":"unhandled","id":"evt_raw","data":{"object":{}}}', headers={"Stripe-Signature":signature}).status_code == 400
    assert len(accepted) == 1
