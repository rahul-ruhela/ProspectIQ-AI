"""Reference data seeded on first boot.

Countries, industries and the service catalogue are real reference data, not sample
prospects. The platform ships with **zero** fake companies, contacts or people.
"""
from __future__ import annotations

# (iso2, iso3, name, continent, phone_code, language)
COUNTRIES: tuple[tuple[str, str, str, str, str, str], ...] = (
    # --- North America ---
    ("US", "USA", "United States", "North America", "+1", "en"),
    ("CA", "CAN", "Canada", "North America", "+1", "en"),
    ("MX", "MEX", "Mexico", "North America", "+52", "es"),
    # --- Europe ---
    ("GB", "GBR", "United Kingdom", "Europe", "+44", "en"),
    ("IE", "IRL", "Ireland", "Europe", "+353", "en"),
    ("DE", "DEU", "Germany", "Europe", "+49", "de"),
    ("FR", "FRA", "France", "Europe", "+33", "fr"),
    ("ES", "ESP", "Spain", "Europe", "+34", "es"),
    ("IT", "ITA", "Italy", "Europe", "+39", "it"),
    ("NL", "NLD", "Netherlands", "Europe", "+31", "nl"),
    ("BE", "BEL", "Belgium", "Europe", "+32", "nl"),
    ("CH", "CHE", "Switzerland", "Europe", "+41", "de"),
    ("AT", "AUT", "Austria", "Europe", "+43", "de"),
    ("SE", "SWE", "Sweden", "Europe", "+46", "sv"),
    ("NO", "NOR", "Norway", "Europe", "+47", "no"),
    ("DK", "DNK", "Denmark", "Europe", "+45", "da"),
    ("FI", "FIN", "Finland", "Europe", "+358", "fi"),
    ("PL", "POL", "Poland", "Europe", "+48", "pl"),
    ("PT", "PRT", "Portugal", "Europe", "+351", "pt"),
    ("CZ", "CZE", "Czechia", "Europe", "+420", "cs"),
    # --- Middle East ---
    ("AE", "ARE", "United Arab Emirates", "Middle East", "+971", "ar"),
    ("SA", "SAU", "Saudi Arabia", "Middle East", "+966", "ar"),
    ("QA", "QAT", "Qatar", "Middle East", "+974", "ar"),
    ("KW", "KWT", "Kuwait", "Middle East", "+965", "ar"),
    ("IL", "ISR", "Israel", "Middle East", "+972", "he"),
    ("TR", "TUR", "Turkey", "Middle East", "+90", "tr"),
    # --- Asia Pacific ---
    ("AU", "AUS", "Australia", "Oceania", "+61", "en"),
    ("NZ", "NZL", "New Zealand", "Oceania", "+64", "en"),
    ("SG", "SGP", "Singapore", "Asia", "+65", "en"),
    ("IN", "IND", "India", "Asia", "+91", "en"),
    ("JP", "JPN", "Japan", "Asia", "+81", "ja"),
    ("MY", "MYS", "Malaysia", "Asia", "+60", "ms"),
    ("PH", "PHL", "Philippines", "Asia", "+63", "en"),
    ("ID", "IDN", "Indonesia", "Asia", "+62", "id"),
    ("HK", "HKG", "Hong Kong", "Asia", "+852", "en"),
    # --- Africa ---
    ("ZA", "ZAF", "South Africa", "Africa", "+27", "en"),
    ("NG", "NGA", "Nigeria", "Africa", "+234", "en"),
    ("KE", "KEN", "Kenya", "Africa", "+254", "en"),
    ("EG", "EGY", "Egypt", "Africa", "+20", "ar"),
    ("MA", "MAR", "Morocco", "Africa", "+212", "fr"),
    # --- South America ---
    ("BR", "BRA", "Brazil", "South America", "+55", "pt"),
    ("AR", "ARG", "Argentina", "South America", "+54", "es"),
    ("CL", "CHL", "Chile", "South America", "+56", "es"),
    ("CO", "COL", "Colombia", "South America", "+57", "es"),
)

# (slug, name, naics, search keywords, ai fit baseline)
# The AI-fit baseline reflects how much of the vertical's work is repetitive
# scheduling, quoting and enquiry handling - the work automation actually removes.
INDUSTRIES: tuple[tuple[str, str, str, str, float], ...] = (
    ("hvac", "HVAC Contractors", "238220",
     "HVAC contractor,heating and cooling company,air conditioning repair,furnace installation", 0.92),
    ("plumbing", "Plumbing Services", "238220",
     "plumber,plumbing company,emergency plumber,drain cleaning service", 0.90),
    ("electrical", "Electrical Contractors", "238210",
     "electrician,electrical contractor,commercial electrician", 0.88),
    ("roofing", "Roofing Contractors", "238160",
     "roofing company,roof repair,roofing contractor", 0.85),
    ("landscaping", "Landscaping & Lawn Care", "561730",
     "landscaping company,lawn care service,garden maintenance", 0.82),
    ("construction", "General Construction", "236220",
     "construction company,general contractor,building contractor", 0.75),
    ("pest_control", "Pest Control", "561710",
     "pest control company,exterminator,termite treatment", 0.88),
    ("cleaning", "Commercial Cleaning", "561720",
     "commercial cleaning company,janitorial service,office cleaning", 0.86),
    ("dental", "Dental Practices", "621210",
     "dental clinic,dentist office,orthodontist practice", 0.90),
    ("medical", "Medical Clinics", "621111",
     "medical clinic,family practice,private clinic", 0.85),
    ("veterinary", "Veterinary Clinics", "541940",
     "veterinary clinic,animal hospital,vet practice", 0.88),
    ("physiotherapy", "Physiotherapy & Chiro", "621340",
     "physiotherapy clinic,chiropractor,sports therapy clinic", 0.87),
    ("legal", "Law Firms", "541110",
     "law firm,solicitors,attorney practice,legal services", 0.80),
    ("accounting", "Accounting & Bookkeeping", "541211",
     "accounting firm,bookkeeping service,tax accountant,CPA firm", 0.86),
    ("real_estate", "Real Estate Agencies", "531210",
     "real estate agency,estate agents,realtor office", 0.84),
    ("property_management", "Property Management", "531311",
     "property management company,letting agent,rental management", 0.87),
    ("insurance", "Insurance Brokers", "524210",
     "insurance broker,insurance agency,commercial insurance", 0.83),
    ("automotive", "Auto Repair & Dealers", "811111",
     "auto repair shop,car garage,mechanic workshop,car dealership", 0.82),
    ("fitness", "Gyms & Fitness Studios", "713940",
     "gym,fitness studio,personal training studio,crossfit box", 0.85),
    ("beauty", "Salons & Spas", "812112",
     "hair salon,beauty spa,nail salon,barbershop", 0.84),
    ("restaurant", "Restaurants & Cafes", "722511",
     "restaurant,cafe,bistro,catering company", 0.72),
    ("hospitality", "Hotels & Hospitality", "721110",
     "hotel,boutique hotel,guest house,bed and breakfast", 0.78),
    ("education", "Training & Education", "611430",
     "training provider,tutoring centre,driving school,language school", 0.83),
    ("logistics", "Logistics & Freight", "484121",
     "freight company,logistics provider,courier service,trucking company", 0.80),
    ("manufacturing", "Small Manufacturing", "332710",
     "manufacturing company,machine shop,fabrication company", 0.70),
    ("wholesale", "Wholesale & Distribution", "423000",
     "wholesale distributor,supply company,trade supplier", 0.74),
    ("ecommerce", "E-commerce Retail", "454110",
     "online store,e-commerce brand,online retailer", 0.76),
    ("marketing_agency", "Marketing Agencies", "541810",
     "marketing agency,digital agency,advertising agency", 0.68),
    ("recruitment", "Recruitment Agencies", "561311",
     "recruitment agency,staffing agency,employment agency", 0.88),
    ("financial_services", "Financial Advisory", "523930",
     "financial advisor,wealth management firm,mortgage broker", 0.82),
    ("security", "Security Services", "561612",
     "security company,alarm installation,cctv installer", 0.84),
    ("moving", "Moving & Removals", "484210",
     "moving company,removals company,relocation service", 0.86),
    ("solar", "Solar & Renewables", "238220",
     "solar installer,solar panel company,renewable energy installer", 0.89),
    ("it_services", "IT Support & MSP", "541512",
     "IT support company,managed service provider,IT consultancy", 0.70),
)

# (slug, name, description, typical deal, trigger feature keys)
SERVICES: tuple[tuple[str, str, str, float, tuple[str, ...]], ...] = (
    ("website_development", "Website Development",
     "A new website built for conversion, speed and search visibility.", 6000.0,
     ("contact_form", "pricing_published", "case_studies")),
    ("website_redesign", "Website Redesign",
     "Rebuild of an outdated or poorly converting site.", 4500.0,
     ("mobile", "stale_site", "testimonials")),
    ("custom_software", "Custom Software",
     "Bespoke internal software replacing spreadsheets and manual process.", 25000.0, ()),
    ("web_application", "Web Application",
     "Customer-facing portal or web app.", 18000.0, ("customer_portal",)),
    ("mobile_application", "Mobile Application",
     "Native or cross-platform mobile app.", 22000.0, ()),
    ("ai_automation", "AI Automation",
     "Automating repetitive operational workflows end to end.", 12000.0,
     ("online_booking", "quote_request")),
    ("ai_agents", "AI Agents",
     "AI assistants that answer, qualify and route enquiries 24/7.", 9000.0,
     ("live_chat", "faq")),
    ("crm_system", "CRM System",
     "CRM implementation so no enquiry is ever lost.", 8000.0, ("crm",)),
    ("marketing_automation", "Marketing Automation",
     "Automated nurture, follow-up and retargeting.", 6500.0,
     ("newsletter_signup", "paid_traffic_leak")),
    ("lead_generation", "Lead Generation System",
     "A measurable inbound lead engine.", 5000.0,
     ("contact_form", "quote_request")),
    ("support_automation", "Customer Support Automation",
     "Deflecting repetitive support contacts automatically.", 7500.0, ("live_chat", "faq")),
    ("document_automation", "Document Automation",
     "Automated quotes, contracts and reports.", 9500.0, ()),
    ("business_dashboard", "Business Dashboard",
     "Live operational and revenue reporting.", 7000.0, ()),
    ("api_integration", "API Integration",
     "Connecting the tools a business already pays for.", 5500.0, ()),
)

# (provider slug, display name, base url)
AI_PROVIDERS: tuple[tuple[str, str, str], ...] = (
    ("anthropic", "Anthropic", "https://api.anthropic.com"),
    ("openai", "OpenAI", "https://api.openai.com/v1"),
    ("google", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta"),
)

# (provider slug, model id, display name, tier, input $/Mtok, output $/Mtok, max output)
# Gemini costs are paid-tier list prices. They are only ever charged if billing is
# enabled on the Google project and LLM_FREE_TIER_ONLY is turned off; under the
# default free-tier guard these models cost nothing.
AI_MODELS: tuple[tuple[str, str, str, str, float, float, int], ...] = (
    ("google", "gemini-3.5-flash", "Gemini 3.5 Flash", "smart", 0.0, 0.0, 8192),
    ("google", "gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite", "cheap", 0.0, 0.0, 8192),
    ("google", "gemini-2.5-flash", "Gemini 2.5 Flash (retired for new projects)",
     "smart", 0.30, 2.50, 8192),
    ("anthropic", "claude-opus-5", "Claude Opus 5", "smart", 5.00, 25.00, 64000),
    ("anthropic", "claude-sonnet-5", "Claude Sonnet 5", "smart", 3.00, 15.00, 64000),
    ("anthropic", "claude-haiku-4-5", "Claude Haiku 4.5", "cheap", 1.00, 5.00, 8192),
    ("openai", "gpt-4o", "GPT-4o", "smart", 2.50, 10.00, 16384),
    ("openai", "gpt-4o-mini", "GPT-4o mini", "cheap", 0.15, 0.60, 16384),
)

# (slug, name, kind, requires key, cost per call, notes)
CONNECTORS: tuple[tuple[str, str, str, bool, float, str], ...] = (
    ("openstreetmap", "OpenStreetMap (Overpass)", "directory", False, 0.0,
     "Keyless structured business records - name, website, phone, address - for mapped "
     "verticals worldwide. Runs before free-text search."),
    ("serper", "Serper (Google Search API)", "search", True, 0.001,
     "Highest quality discovery. Set SERPER_API_KEY."),
    ("google_cse", "Google Programmable Search", "search", True, 0.005,
     "Official Google API. Set GOOGLE_CSE_KEY and GOOGLE_CSE_CX."),
    ("searxng", "SearXNG (self-hosted)", "search", False, 0.0,
     "Free meta-search if you run your own instance. Set SEARXNG_URL."),
    ("duckduckgo", "DuckDuckGo HTML", "search", False, 0.0,
     "Keyless fallback so a fresh install can discover companies immediately. Rate limited."),
    ("website_crawler", "Website Crawler", "enrichment", False, 0.0,
     "First-party crawler. Honours robots.txt and rate limits."),
    ("dns_mx", "DNS / MX Verification", "enrichment", False, 0.0,
     "Validates email domains without probing mailboxes."),
)
