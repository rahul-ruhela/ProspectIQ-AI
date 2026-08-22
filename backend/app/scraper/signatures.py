"""Technology fingerprints and website-capability signals.

Each signature is a substring that, when found in the raw HTML, headers or cookies,
is direct evidence of the technology. The matched string is stored so a human can
audit every detection.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TechSignature:
    slug: str
    name: str
    category: str
    html_patterns: tuple[str, ...] = ()
    header_patterns: tuple[tuple[str, str], ...] = ()
    url_patterns: tuple[str, ...] = ()
    version_regex: str | None = None


TECH_SIGNATURES: tuple[TechSignature, ...] = (
    # --- CMS / site builders ---
    TechSignature(
        "wordpress", "WordPress", "cms",
        html_patterns=("/wp-content/", "/wp-includes/", 'name="generator" content="WordPress'),
        version_regex=r'name="generator" content="WordPress ([0-9.]+)',
    ),
    TechSignature("shopify", "Shopify", "ecommerce",
                  html_patterns=("cdn.shopify.com", "Shopify.theme", "shopify-section")),
    TechSignature("wix", "Wix", "cms",
                  html_patterns=("static.wixstatic.com", "wix-code", "X-Wix-")),
    TechSignature("squarespace", "Squarespace", "cms",
                  html_patterns=("static1.squarespace.com", "squarespace-config")),
    TechSignature("webflow", "Webflow", "cms",
                  html_patterns=("assets.website-files.com", "webflow.js", 'data-wf-site')),
    TechSignature("drupal", "Drupal", "cms",
                  html_patterns=("/sites/default/files/", "drupal-settings-json")),
    TechSignature("joomla", "Joomla", "cms", html_patterns=("/media/jui/", "joomla-script-options")),
    TechSignature("duda", "Duda", "cms", html_patterns=("irp.cdn-website.com", "duda_website")),
    TechSignature("godaddy_builder", "GoDaddy Website Builder", "cms",
                  html_patterns=("img1.wsimg.com", "godaddy-website-builder")),
    # --- frontend frameworks ---
    TechSignature("react", "React", "frontend",
                  html_patterns=("data-reactroot", "__NEXT_DATA__", "react-dom")),
    TechSignature("nextjs", "Next.js", "frontend",
                  html_patterns=("/_next/static/", "__NEXT_DATA__")),
    TechSignature("angular", "Angular", "frontend",
                  html_patterns=("ng-version=", "ng-app", "angular.min.js")),
    TechSignature("vue", "Vue.js", "frontend", html_patterns=("data-v-", "vue.runtime", "__NUXT__")),
    TechSignature("jquery", "jQuery", "frontend", html_patterns=("jquery.min.js", "jquery-3.")),
    TechSignature("bootstrap", "Bootstrap", "frontend", html_patterns=("bootstrap.min.css",)),
    TechSignature("tailwind", "Tailwind CSS", "frontend", html_patterns=("tailwindcss", "tw-")),
    # --- CRM / marketing automation ---
    TechSignature("hubspot", "HubSpot", "crm",
                  html_patterns=("js.hs-scripts.com", "hs-analytics", "hsforms.net")),
    TechSignature("salesforce", "Salesforce", "crm",
                  html_patterns=("force.com", "salesforce.com/embeddedservice", "pardot")),
    TechSignature("zoho", "Zoho", "crm", html_patterns=("zohopublic", "zoho.com/crm", "zohocdn")),
    TechSignature("gohighlevel", "GoHighLevel", "crm",
                  html_patterns=("msgsndr.com", "leadconnectorhq", "gohighlevel")),
    TechSignature("mailchimp", "Mailchimp", "marketing",
                  html_patterns=("chimpstatic.com", "list-manage.com")),
    TechSignature("klaviyo", "Klaviyo", "marketing", html_patterns=("static.klaviyo.com",)),
    TechSignature("activecampaign", "ActiveCampaign", "marketing",
                  html_patterns=("prism.app-us1.com", "activehosted.com")),
    # --- booking / scheduling ---
    TechSignature("calendly", "Calendly", "booking", html_patterns=("assets.calendly.com", "calendly.com/")),
    TechSignature("acuity", "Acuity Scheduling", "booking", html_patterns=("acuityscheduling.com",)),
    TechSignature("housecallpro", "Housecall Pro", "field_service",
                  html_patterns=("housecallpro.com", "hcp-booking")),
    TechSignature("servicetitan", "ServiceTitan", "field_service", html_patterns=("servicetitan.com",)),
    TechSignature("jobber", "Jobber", "field_service", html_patterns=("getjobber.com", "jobber.com/")),
    # --- payments ---
    TechSignature("stripe", "Stripe", "payments", html_patterns=("js.stripe.com", "stripe.com/v3")),
    TechSignature("paypal", "PayPal", "payments", html_patterns=("paypal.com/sdk", "paypalobjects.com")),
    TechSignature("square", "Square", "payments", html_patterns=("squareup.com", "squarecdn.com")),
    # --- analytics / advertising ---
    TechSignature("google_analytics", "Google Analytics", "analytics",
                  html_patterns=("google-analytics.com/analytics.js", "gtag('config'", "googletagmanager.com/gtag/js")),
    TechSignature("google_tag_manager", "Google Tag Manager", "analytics",
                  html_patterns=("googletagmanager.com/gtm.js", "GTM-")),
    TechSignature("meta_pixel", "Meta Pixel", "advertising",
                  html_patterns=("connect.facebook.net", "fbq('init'")),
    TechSignature("hotjar", "Hotjar", "analytics", html_patterns=("static.hotjar.com",)),
    TechSignature("linkedin_insight", "LinkedIn Insight Tag", "advertising",
                  html_patterns=("snap.licdn.com",)),
    TechSignature("tiktok_pixel", "TikTok Pixel", "advertising", html_patterns=("analytics.tiktok.com",)),
    # --- chat / support ---
    TechSignature("intercom", "Intercom", "support", html_patterns=("widget.intercom.io", "intercomcdn")),
    TechSignature("drift", "Drift", "support", html_patterns=("js.driftt.com",)),
    TechSignature("tawkto", "Tawk.to", "support", html_patterns=("embed.tawk.to",)),
    TechSignature("zendesk", "Zendesk", "support", html_patterns=("static.zdassets.com", "zendesk.com/embeddable")),
    TechSignature("livechat", "LiveChat", "support", html_patterns=("cdn.livechatinc.com",)),
    TechSignature("crisp", "Crisp", "support", html_patterns=("client.crisp.chat",)),
    # --- infrastructure ---
    TechSignature("cloudflare", "Cloudflare", "infrastructure",
                  header_patterns=(("server", "cloudflare"), ("cf-ray", ""))),
    TechSignature("nginx", "nginx", "infrastructure", header_patterns=(("server", "nginx"),)),
    TechSignature("apache", "Apache", "infrastructure", header_patterns=(("server", "apache"),)),
    TechSignature("vercel", "Vercel", "infrastructure", header_patterns=(("server", "vercel"),)),
    TechSignature("netlify", "Netlify", "infrastructure", header_patterns=(("server", "netlify"),)),
)


@dataclass(slots=True)
class TechMatch:
    slug: str
    name: str
    category: str
    matched_signature: str
    source_url: str
    version: str | None = None
    confidence: float = 0.9


def detect_technologies(html: str, headers: dict[str, str], url: str) -> list[TechMatch]:
    matches: list[TechMatch] = []
    lowered = html.lower()
    for signature in TECH_SIGNATURES:
        matched: str | None = None
        confidence = 0.9
        for pattern in signature.html_patterns:
            if pattern.lower() in lowered:
                matched = pattern
                break
        if matched is None:
            for header, needle in signature.header_patterns:
                value = headers.get(header, "").lower()
                if value and (not needle or needle in value):
                    matched = f"{header}: {value[:60]}"
                    confidence = 0.85
                    break
        if matched is None:
            continue
        version = None
        if signature.version_regex:
            found = re.search(signature.version_regex, html, re.IGNORECASE)
            if found:
                version = found.group(1)
        matches.append(
            TechMatch(
                slug=signature.slug,
                name=signature.name,
                category=signature.category,
                matched_signature=matched[:400],
                source_url=url,
                version=version,
                confidence=confidence,
            )
        )
    return matches


# --- website capability signals -------------------------------------------------
# Feature keys are stable identifiers referenced by the service catalogue and scoring.

FEATURE_SIGNALS: dict[str, tuple[str, ...]] = {
    "contact_form": ("form",),
    "live_chat": ("intercom", "tawk", "drift", "livechat", "crisp", "zendesk", "chatbot", "hubspot-messages"),
    "online_booking": ("calendly", "acuityscheduling", "book now", "book online", "schedule an appointment", "request appointment"),
    "ecommerce": ("add to cart", "shopping cart", "checkout", "shopify", "woocommerce"),
    "customer_portal": ("client portal", "customer portal", "my account", "sign in", "log in"),
    "newsletter_signup": ("newsletter", "subscribe", "mailing list"),
    "testimonials": ("testimonial", "what our clients say", "reviews"),
    "case_studies": ("case study", "case studies", "success story"),
    "pricing_published": ("pricing", "our prices", "$", "price list"),
    "blog": ("blog", "latest news", "articles"),
    "faq": ("frequently asked", "faq"),
    "trust_badges": ("licensed", "insured", "certified", "accredited", "bbb", "google reviews"),
    "quote_request": ("get a quote", "request a quote", "free estimate", "free quote"),
    "whatsapp": ("wa.me/", "api.whatsapp.com"),
    "emergency_service": ("24/7", "24 hours", "emergency service"),
    "multilingual": ("hreflang",),
}

# Features whose absence is a concrete, sellable opportunity.
OPPORTUNITY_FEATURES: dict[str, str] = {
    "online_booking": "No online booking - bookings depend on phone calls during office hours.",
    "live_chat": "No live chat or chatbot - website visitors have no instant answer path.",
    "contact_form": "No contact form - the only conversion path is a phone number.",
    "quote_request": "No quote request flow - inbound demand is not captured.",
    "customer_portal": "No customer portal - status requests fall to staff.",
    "pricing_published": "No published pricing - visitors leave to compare elsewhere.",
    "case_studies": "No case studies or proof - weak trust building for larger jobs.",
    "newsletter_signup": "No email capture - traffic is not retargetable.",
}
