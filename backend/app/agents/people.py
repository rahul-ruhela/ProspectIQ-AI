"""Decision Maker, Contact Enrichment, Email Verification and Phone Intelligence agents."""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import dns.exception
import dns.resolver
import phonenumbers
from phonenumbers import carrier as pn_carrier
from phonenumbers import number_type as pn_number_type

from app.agents.base import AgentContext, AgentResult, BaseAgent
from app.agents.utils import load_company
from app.agents.website import get_cached_crawl
from app.models.company import Contact, DecisionMaker, EmailVerification, PhoneVerification
from app.models.enums import (
    AgentName,
    EmailQuality,
    PhoneLineType,
    VerificationStatus,
)
from app.scraper.extract import ROLE_EMAIL_PREFIXES, extract_people

FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com", "icloud.com",
    "live.com", "msn.com", "gmx.com", "gmx.de", "web.de", "mail.com", "yandex.com",
    "protonmail.com", "proton.me", "zoho.com", "orange.fr", "free.fr", "t-online.de",
    "me.com", "mac.com", "ymail.com", "rocketmail.com", "comcast.net", "sbcglobal.net",
    "verizon.net", "btinternet.com", "sky.com", "bigpond.com", "optusnet.com.au",
    "hotmail.co.uk", "yahoo.co.uk", "yahoo.ca", "hotmail.fr", "yahoo.fr", "yahoo.de",
    "outlook.de", "outlook.fr", "libero.it", "naver.com", "qq.com", "163.com",
}

# A representative slice of throwaway-mail providers. Operators extend this via the
# admin connector config; unknown domains are reported as unknown, never as valid.
DISPOSABLE_EMAIL_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "temp-mail.org", "throwawaymail.com", "yopmail.com", "trashmail.com",
    "sharklasers.com", "getnada.com", "dispostable.com", "maildrop.cc",
    "fakeinbox.com", "mailnesia.com", "spam4.me", "moakt.com", "emailondeck.com",
}

PHONE_TYPE_MAP = {
    phonenumbers.PhoneNumberType.FIXED_LINE: PhoneLineType.FIXED_LINE,
    phonenumbers.PhoneNumberType.MOBILE: PhoneLineType.MOBILE,
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: PhoneLineType.UNKNOWN,
    phonenumbers.PhoneNumberType.TOLL_FREE: PhoneLineType.TOLL_FREE,
    phonenumbers.PhoneNumberType.VOIP: PhoneLineType.VOIP,
}


class DecisionMakerAgent(BaseAgent):
    """Finds named owners and executives on the company's own pages."""

    key = AgentName.DECISION_MAKER
    display_name = "Decision Maker Agent"
    role = "People Researcher"
    goal = (
        "Identify founders, owners, CEOs, presidents, COOs, managing directors and "
        "marketing/IT leaders, each with the page that names them."
    )
    tools = ("team_page_parser", "role_matcher")
    input_schema = {
        "type": "object",
        "properties": {"company_id": {"type": "string"}},
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "decision_makers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "full_name": {"type": "string"},
                        "role_title": {"type": "string"},
                        "source_url": {"type": "string"},
                    },
                },
            }
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")
        crawl = get_cached_crawl(str(company.id))
        if crawl is None or not crawl.pages:
            self.log(ctx, f"No crawl data for {company.name}; decision makers unknown.")
            return AgentResult(ok=True, data={"decision_makers": [], "reason": "no_crawl_data"}, confidence=0.0)

        # Team and about pages carry the reliable attributions; the homepage is noisier.
        ordered = sorted(
            crawl.pages,
            key=lambda p: {"team": 0, "about": 1, "contact": 2, "homepage": 3}.get(p.page_type, 4),
        )
        existing = {dm.full_name.lower() for dm in company.decision_makers}
        found: list[dict[str, str]] = []

        for page in ordered[:6]:
            for person in extract_people(page):
                if person.full_name.lower() in existing:
                    continue
                existing.add(person.full_name.lower())
                # A team/about page attribution is far stronger than a homepage sentence.
                confidence = 0.85 if page.page_type in ("team", "about") else 0.65
                company.decision_makers.append(
                    DecisionMaker(
                        full_name=person.full_name[:200],
                        role_title=person.role_title[:200],
                        role_category=person.role_category,
                        seniority=person.seniority,
                        profile_url=person.profile_url,
                        linkedin_url=person.linkedin_url,
                        bio=person.context[:2000],
                        source=f"Company website ({page.page_type})",
                        source_url=person.found_on_url,
                        confidence=confidence,
                        verification_status=VerificationStatus.VERIFIED,
                        last_verified_at=datetime.now(UTC),
                    )
                )
                found.append(
                    {
                        "full_name": person.full_name,
                        "role_title": person.role_title,
                        "role_category": person.role_category,
                        "source_url": person.found_on_url,
                    }
                )

        if not found:
            self.log(
                ctx,
                f"No decision maker named on {company.domain}. Stored as unknown rather than guessed.",
            )
        else:
            self.log(ctx, f"Found {len(found)} decision maker(s) for {company.name}.")

        return AgentResult(
            ok=True,
            data={"decision_makers": found},
            confidence=0.85 if found else 0.2,
        )


class ContactEnrichmentAgent(BaseAgent):
    """Collects business emails and phone numbers published by the company."""

    key = AgentName.CONTACT_ENRICHMENT
    display_name = "Contact Enrichment Agent"
    role = "Contact Researcher"
    goal = (
        "Collect publicly published business emails and phone numbers from the company's "
        "own pages, recording the exact page each one appeared on."
    )
    tools = ("page_scanner", "mailto_parser", "tel_parser")
    input_schema = {
        "type": "object",
        "properties": {"company_id": {"type": "string"}},
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "emails": {"type": "array", "items": {"type": "string"}},
            "phones": {"type": "array", "items": {"type": "string"}},
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")
        crawl = get_cached_crawl(str(company.id))
        if crawl is None or not crawl.pages:
            return AgentResult(ok=True, data={"emails": [], "phones": []}, confidence=0.0)

        known = {contact.value.lower() for contact in company.contacts}
        emails: list[str] = []
        phones: list[str] = []
        # Contact pages first so the primary address is the one the business advertises.
        ordered = sorted(
            crawl.pages, key=lambda p: 0 if p.page_type in ("contact", "homepage") else 1
        )

        for page in ordered:
            for email in page.emails:
                value = email.value.lower()
                if value in known:
                    continue
                known.add(value)
                domain = value.split("@")[-1]
                on_domain = company.domain is not None and domain.endswith(company.domain)
                company.contacts.append(
                    Contact(
                        contact_type="email",
                        value=value[:320],
                        label="role" if email.is_role_account else ("personal" if on_domain else "external"),
                        is_primary=not emails,
                        found_on_url=email.found_on_url,
                        source=f"Company website ({page.page_type})",
                        source_url=email.found_on_url,
                        # Same-domain addresses are the ones we can actually trust.
                        confidence=0.9 if on_domain else 0.6,
                        verification_status=VerificationStatus.NEEDS_VERIFICATION,
                    )
                )
                emails.append(value)
                if on_domain and not company.primary_email:
                    company.primary_email = value

            for phone in page.phones:
                digits = re.sub(r"[^\d+]", "", phone.value)
                if len(digits) < 7 or digits in known:
                    continue
                known.add(digits)
                company.contacts.append(
                    Contact(
                        contact_type="phone",
                        value=phone.value[:60],
                        label="business",
                        is_primary=not phones,
                        found_on_url=phone.found_on_url,
                        source=f"Company website ({page.page_type})",
                        source_url=phone.found_on_url,
                        confidence=0.85,
                        verification_status=VerificationStatus.NEEDS_VERIFICATION,
                    )
                )
                phones.append(phone.value)
                if not company.phone:
                    company.phone = phone.value[:60]

        # Attach role-free personal addresses to a matching decision maker where the
        # local part clearly corresponds to their name.
        for contact in company.contacts:
            if contact.contact_type != "email" or contact.decision_maker_id:
                continue
            local = contact.value.split("@")[0].lower()
            if local in ROLE_EMAIL_PREFIXES:
                continue
            for dm in company.decision_makers:
                parts = [p.lower() for p in dm.full_name.split() if len(p) > 2]
                if parts and all(p[:4] in local for p in parts[:2]):
                    contact.decision_maker = dm
                    contact.label = "decision_maker"
                    break

        self.log(
            ctx,
            f"Collected {len(emails)} email(s) and {len(phones)} phone number(s) for {company.name}.",
        )
        return AgentResult(
            ok=True,
            data={"emails": emails, "phones": phones},
            confidence=0.85 if (emails or phones) else 0.2,
        )


class EmailVerificationAgent(BaseAgent):
    """Validates syntax, domain, MX records and address type. No mailbox probing."""

    key = AgentName.EMAIL_VERIFICATION
    display_name = "Email Verification Agent"
    role = "Deliverability Analyst"
    goal = (
        "Verify each collected address: syntax, resolvable domain, MX records, "
        "disposable/free/role classification and a calibrated confidence."
    )
    tools = ("dns_resolver", "mx_lookup", "disposable_list")
    input_schema = {
        "type": "object",
        "properties": {"company_id": {"type": "string"}},
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {
            "verified": {"type": "integer"},
            "results": {"type": "array", "items": {"type": "object"}},
        },
    }

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")

        results: list[dict[str, Any]] = []
        mx_cache: dict[str, tuple[bool, list[str]]] = {}

        for contact in company.contacts:
            if contact.contact_type != "email" or contact.email_verification is not None:
                continue
            email = contact.value.lower()
            syntax_ok = bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", email))
            domain = email.rsplit("@", 1)[-1] if "@" in email else ""
            local = email.split("@")[0]

            has_mx, mx_hosts = (False, [])
            if syntax_ok and domain:
                if domain not in mx_cache:
                    mx_cache[domain] = _lookup_mx(domain)
                has_mx, mx_hosts = mx_cache[domain]

            is_disposable = domain in DISPOSABLE_EMAIL_DOMAINS
            is_free = domain in FREE_EMAIL_DOMAINS
            is_role = local in ROLE_EMAIL_PREFIXES

            if not syntax_ok:
                quality, status, confidence = EmailQuality.INVALID, VerificationStatus.REJECTED, 0.0
            elif is_disposable:
                quality, status, confidence = EmailQuality.DISPOSABLE, VerificationStatus.REJECTED, 0.1
            elif not has_mx:
                # No MX means nothing can be delivered - but DNS can also be blocked
                # from this host, so we say "needs verification" rather than "invalid".
                quality, status, confidence = EmailQuality.UNKNOWN, VerificationStatus.NEEDS_VERIFICATION, 0.25
            elif is_role:
                quality, status, confidence = EmailQuality.ROLE, VerificationStatus.VERIFIED, 0.8
            elif is_free:
                quality, status, confidence = EmailQuality.PERSONAL, VerificationStatus.VERIFIED, 0.6
            else:
                quality, status, confidence = EmailQuality.BUSINESS, VerificationStatus.VERIFIED, 0.9

            contact.email_verification = EmailVerification(
                email=email,
                syntax_valid=syntax_ok,
                domain_resolves=has_mx or None,
                has_mx=has_mx,
                mx_hosts=mx_hosts,
                is_disposable=is_disposable,
                is_free_provider=is_free,
                is_role_account=is_role,
                quality=quality,
                status=status,
                confidence=confidence,
                checked_at=datetime.now(UTC),
            )
            contact.verification_status = status
            contact.confidence = round((contact.confidence + confidence) / 2, 3)
            contact.last_verified_at = datetime.now(UTC)
            results.append({"email": email, "quality": str(quality), "confidence": confidence})

        self.log(ctx, f"Verified {len(results)} email address(es) for {company.name}.")
        return AgentResult(
            ok=True,
            data={"verified": len(results), "results": results},
            confidence=0.9 if results else 0.3,
        )


class PhoneIntelligenceAgent(BaseAgent):
    """Normalises numbers to E.164 and classifies line type and WhatsApp likelihood."""

    key = AgentName.PHONE_INTELLIGENCE
    display_name = "Phone Intelligence Agent"
    role = "Telephony Analyst"
    goal = (
        "Normalise every collected number to E.164, resolve its country and line type, "
        "and flag whether WhatsApp outreach is plausible."
    )
    tools = ("phonenumbers", "carrier_lookup")
    input_schema = {
        "type": "object",
        "properties": {"company_id": {"type": "string"}},
        "required": ["company_id"],
    }
    output_schema = {
        "type": "object",
        "properties": {"verified": {"type": "integer"}, "results": {"type": "array", "items": {"type": "object"}}},
    }

    # Markets where WhatsApp is the default business channel.
    WHATSAPP_MARKETS = {"AE", "IN", "BR", "MX", "ZA", "NG", "ID", "ES", "IT", "SA", "EG", "PK"}

    async def run(self, ctx: AgentContext, payload: dict[str, Any]) -> AgentResult:
        company = load_company(ctx, payload)
        if company is None:
            return AgentResult.failure("company_not_found")

        results: list[dict[str, Any]] = []
        region = company.country_code

        for contact in company.contacts:
            if contact.contact_type != "phone" or contact.phone_verification is not None:
                continue
            raw = contact.value
            try:
                parsed = phonenumbers.parse(raw, region)
            except phonenumbers.NumberParseException:
                contact.phone_verification = PhoneVerification(
                    raw_value=raw[:60],
                    is_valid=False,
                    status=VerificationStatus.REJECTED,
                    confidence=0.0,
                    checked_at=datetime.now(UTC),
                )
                contact.verification_status = VerificationStatus.REJECTED
                continue

            valid = phonenumbers.is_valid_number(parsed)
            e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164) if valid else None
            country = phonenumbers.region_code_for_number(parsed) if valid else None
            line_type = PHONE_TYPE_MAP.get(pn_number_type(parsed), PhoneLineType.UNKNOWN)
            carrier_name = pn_carrier.name_for_number(parsed, "en") or None
            whatsapp = (
                line_type == PhoneLineType.MOBILE
                and country in self.WHATSAPP_MARKETS
            ) if valid else None

            contact.phone_verification = PhoneVerification(
                raw_value=raw[:60],
                e164=e164,
                country_code=country,
                dial_code=f"+{parsed.country_code}" if valid else None,
                line_type=line_type,
                carrier=carrier_name,
                is_valid=valid,
                whatsapp_likely=whatsapp,
                status=VerificationStatus.VERIFIED if valid else VerificationStatus.REJECTED,
                confidence=0.9 if valid else 0.0,
                checked_at=datetime.now(UTC),
            )
            contact.verification_status = (
                VerificationStatus.VERIFIED if valid else VerificationStatus.REJECTED
            )
            contact.last_verified_at = datetime.now(UTC)
            if valid and e164:
                results.append({"e164": e164, "line_type": str(line_type), "country": country})
                if not company.phone or company.phone == raw:
                    company.phone = e164

        self.log(ctx, f"Validated {len(results)} phone number(s) for {company.name}.")
        return AgentResult(
            ok=True,
            data={"verified": len(results), "results": results},
            confidence=0.9 if results else 0.3,
        )


def _lookup_mx(domain: str) -> tuple[bool, list[str]]:
    """Return (has_mx, hosts). DNS failures yield no claim rather than a false negative."""
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5.0)
        hosts = sorted(str(rdata.exchange).rstrip(".") for rdata in answers)
        return bool(hosts), hosts[:5]
    except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
        return False, []
    except (dns.exception.Timeout, dns.exception.DNSException):
        return False, []
