class BillingError(RuntimeError):
    code = "BILLING_ERROR"


class BillingNotConfigured(BillingError): code = "BILLING_NOT_CONFIGURED"
class BillingProviderError(BillingError): code = "BILLING_PROVIDER_UNAVAILABLE"
class InvalidWebhookSignature(BillingError): code = "BILLING_INVALID_WEBHOOK_SIGNATURE"
class UnsupportedSubscriptionShape(BillingError): code = "BILLING_UNSUPPORTED_SUBSCRIPTION_SHAPE"
class UnmappedStripePrice(BillingError): code = "BILLING_PRICE_UNMAPPED"
class BillingOwnershipError(BillingError): code = "BILLING_OWNERSHIP_MISMATCH"

