"""Tests for the rules that keep fabricated data out of the database.

These cover the extraction and classification logic that decides whether something
becomes a stored fact. Each case below corresponds to a false positive that was
actually observed against live websites during development.
"""
from __future__ import annotations

import pytest

from app.agents.discovery import clean_company_name
from app.agents.people import DISPOSABLE_EMAIL_DOMAINS, FREE_EMAIL_DOMAINS
from app.agents.signals import SIGNAL_EXCLUDED_PAGE_TYPES, SIGNAL_PATTERNS, _find_phrase
from app.models.enums import ScoreCategory
from app.scraper.crawler import domain_of, normalise_url
from app.scraper.extract import (
    classify_page,
    extract_people,
    looks_like_person_name,
    looks_like_role_title,
    parse_page,
)
from app.scraper.signatures import detect_technologies


# --- person extraction ---------------------------------------------------------


@pytest.mark.parametrize(
    "candidate",
    ["Jane Smith", "Molly Drazic", "George Drazic", "Shane Bryant", "Mary-Ann O'Neill"],
)
def test_real_names_are_accepted(candidate: str) -> None:
    assert looks_like_person_name(candidate)


@pytest.mark.parametrize(
    "candidate",
    [
        "Maintenance Between Cleanings",  # observed false positive on a live HVAC site
        "Air Duct Cleaning",
        "Our Services",
        "Emergency Repair Services",
        "Free Quote Today",
        "Why Choose Us",
        "Smith",  # single token is not a full name
    ],
)
def test_marketing_headings_are_not_people(candidate: str) -> None:
    assert not looks_like_person_name(candidate)


def test_role_title_rejects_body_copy() -> None:
    assert looks_like_role_title("Founder & CEO")
    assert looks_like_role_title("Managing Director")
    assert not looks_like_role_title(
        "Although having your air ducts professionally cleaned is beneficial to your "
        "home and health, it isn't enough to guarantee clean air."
    )


def test_extract_people_requires_name_and_title_together() -> None:
    html = """
    <html><body>
      <div><h3>Molly Drazic</h3><p>CEO</p></div>
      <div><h3>Maintenance Between Cleanings</h3>
           <p>Although having your air ducts professionally cleaned is beneficial,
              it is not enough to guarantee clean air in your home.</p></div>
      <div><h3>Our Services</h3><p>Owner</p></div>
    </body></html>
    """
    people = extract_people(parse_page("https://example.com/about", html))
    names = {p.full_name for p in people}
    assert "Molly Drazic" in names
    assert "Maintenance Between Cleanings" not in names
    assert "Our Services" not in names


# --- buying signals ------------------------------------------------------------


def test_phrase_matching_respects_word_boundaries() -> None:
    # "we raised the bar" must not read as a funding event.
    assert _find_phrase("we raised the bar for service", "raised funding") == -1
    assert _find_phrase("we raised funding last year", "raised funding") == 3
    assert _find_phrase("nowhere offering that", "now offering") == -1
    assert _find_phrase("we are now offering ac tune-ups", "now offering") == 7


def test_legal_pages_are_excluded_from_signals() -> None:
    # A privacy policy produced a bogus "new service" signal before this exclusion.
    assert classify_page("https://example.com/privacy-policy") == "legal"
    assert "legal" in SIGNAL_EXCLUDED_PAGE_TYPES


def test_no_signal_pattern_is_a_bare_generic_word() -> None:
    banned = {"raised", "doubled", "award-winning", "expanding", "growing"}
    for patterns in SIGNAL_PATTERNS.values():
        for phrase, _strength in patterns:
            assert phrase not in banned, f"{phrase!r} is too generic to be evidence"


# --- email classification ------------------------------------------------------


def test_consumer_mailbox_providers_are_not_business_addresses() -> None:
    for domain in ("gmail.com", "me.com", "icloud.com", "yahoo.com", "outlook.com"):
        assert domain in FREE_EMAIL_DOMAINS


def test_disposable_domains_are_known() -> None:
    assert "mailinator.com" in DISPOSABLE_EMAIL_DOMAINS


# --- page parsing --------------------------------------------------------------


def test_parse_page_extracts_contacts_with_their_page() -> None:
    html = """
    <html lang="en"><head><title>Contact | Acme HVAC</title>
      <meta name="description" content="Get in touch">
      <meta name="viewport" content="width=device-width">
    </head><body>
      <h1>Contact us</h1>
      <a href="mailto:hello@acmehvac.com">Email us</a>
      <a href="tel:+15125551234">Call us</a>
      <form><input name="email"><textarea name="msg"></textarea></form>
      <p>&copy; 2019 Acme HVAC</p>
    </body></html>
    """
    page = parse_page("https://acmehvac.com/contact", html)
    assert page.page_type == "contact"
    assert page.title == "Contact | Acme HVAC"
    assert page.has_viewport_meta is True
    assert page.copyright_year == 2019
    assert page.forms_count == 1
    assert [e.value for e in page.emails] == ["hello@acmehvac.com"]
    assert page.emails[0].found_on_url == "https://acmehvac.com/contact"
    assert page.phones and page.phones[0].found_on_url == "https://acmehvac.com/contact"


def test_asset_filenames_are_not_treated_as_emails() -> None:
    html = '<html><body><img src="logo@2x.png"><p>logo@2x.png</p></body></html>'
    assert parse_page("https://example.com", html).emails == []


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/", "homepage"),
        ("https://example.com/about-us", "about"),
        ("https://example.com/careers", "careers"),
        ("https://example.com/book-online", "booking"),
        ("https://example.com/our-team", "team"),
        ("https://example.com/terms-of-service", "legal"),
    ],
)
def test_page_classification(url: str, expected: str) -> None:
    assert classify_page(url) == expected


# --- technology detection ------------------------------------------------------


def test_technology_detection_records_the_matching_signature() -> None:
    html = '<html><head><link href="/wp-content/themes/x/style.css"></head><body></body></html>'
    matches = detect_technologies(html, {}, "https://example.com")
    wordpress = next(m for m in matches if m.slug == "wordpress")
    assert wordpress.matched_signature == "/wp-content/"
    assert wordpress.source_url == "https://example.com"


def test_technology_detection_reads_headers() -> None:
    matches = detect_technologies("<html></html>", {"server": "nginx/1.25"}, "https://example.com")
    assert any(m.slug == "nginx" for m in matches)


# --- url normalisation ---------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "example.com"),
        ("https://www.Example.com/path", "example.com"),
        ("http://sub.example.co.uk/", "sub.example.co.uk"),
        ("", ""),
    ],
)
def test_domain_of(raw: str, expected: str) -> None:
    assert domain_of(raw) == expected


def test_normalise_url_adds_scheme_and_strips_query() -> None:
    assert normalise_url("example.com/page?utm=1") == "https://example.com/page"


# --- company naming ------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "domain", "expected"),
    [
        ("Acme HVAC | Home", "acmehvac.com", "Acme HVAC"),
        ("Acme HVAC - Official Site", "acmehvac.com", "Acme HVAC"),
        ("", "acme-hvac.com", "Acme Hvac"),
    ],
)
def test_clean_company_name(title: str, domain: str, expected: str) -> None:
    assert clean_company_name(title, domain) == expected


# --- scoring bands -------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "category"),
    [
        (95, ScoreCategory.EXCEPTIONAL),
        (90, ScoreCategory.EXCEPTIONAL),
        (89.9, ScoreCategory.HIGH_PRIORITY),
        (75, ScoreCategory.HIGH_PRIORITY),
        (60, ScoreCategory.MEDIUM),
        (40, ScoreCategory.LOW),
        (0, ScoreCategory.POOR),
    ],
)
def test_score_categories_match_the_spec(score: float, category: ScoreCategory) -> None:
    assert ScoreCategory.from_score(score) == category
