import os
import stripe

# Load your secret key from the env
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

cfg = stripe.billing_portal.Configuration.create(
    business_profile={
        "headline": "Manage your Tweenleaf subscription",
        "privacy_policy_url": "https://versanestemporium.com/privacy",
        "terms_of_service_url": "https://versanestemporium.com/terms"
    },
    features={
        # Enable payment method updates
        "payment_method_update": {"enabled": True},
        # Enable subscription updates
        "subscription_update": {
            "enabled": True,
            "products": [
                {
                    "product": "prod_SEp1XpbDUfGKsf",
                    "prices": ["price_1RKLNsCS2zzOISLkStFc2hmJ"]
                }
            ],
            "default_allowed_updates": ["price"]
        },
        # Enable subscription cancellations
        "subscription_cancel": {"enabled": True},
    },
    default_return_url=os.getenv("TIKTOK_REDIRECT_URI")
)

print("Created portal configuration:", cfg.id)
