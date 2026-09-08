import json
import os

import pytest

from backend.filters.experience import check_experience, extract_min_years
from backend.filters.location import classify_location, TIER_A, TIER_B, TIER_C, TIER_D
from backend.filters.pipeline import run_hard_filters
from backend.filters.role import check_role
from backend.models import Job

PREFS_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "preferences.json")


@pytest.fixture(scope="module")
def prefs():
    with open(PREFS_PATH) as f:
        return json.load(f)


# ---------- experience ----------

def test_extract_min_years_plus_pattern():
    assert extract_min_years("5+ years of experience required") == 5


def test_extract_min_years_range_pattern():
    assert extract_min_years("2-4 years of product management experience") == 2


def test_extract_min_years_none_when_unstated():
    assert extract_min_years("Great team, fast-growing startup, remote-first culture.") is None


def test_experience_hard_rejects_seven_plus(prefs):
    res = check_experience("Product Manager", "Requires 7+ years of experience in SaaS.", prefs)
    assert res.passed is False


def test_experience_rejects_senior_title_even_without_years(prefs):
    res = check_experience("Senior Product Manager", "Great opportunity for an experienced PM.", prefs)
    assert res.passed is False


def test_experience_allows_senior_qa_exception(prefs):
    # QA seniority ladders differ from PM ones - "Senior QA" shouldn't auto-reject.
    res = check_experience("Senior QA Engineer", "2+ years of QA experience.", prefs)
    assert res.passed is True


def test_experience_five_to_six_passes_but_flags_realism_check(prefs):
    res = check_experience("Product Manager", "5 years of experience required.", prefs)
    assert res.passed is True
    assert res.detail["needs_realism_check"] is True


def test_experience_two_to_four_passes_cleanly(prefs):
    res = check_experience("Product Manager", "2-4 years of experience preferred.", prefs)
    assert res.passed is True
    assert not res.detail.get("needs_realism_check")


def test_experience_unstated_passes_without_realism_flag(prefs):
    res = check_experience("Product Manager", "Join our growing team!", prefs)
    assert res.passed is True
    assert res.detail["years_required"] is None


# ---------- location ----------

def _job(location_raw="", hires_remotely_from=None, description=""):
    return Job(source="s", external_id="1", title="Product Manager", company="Acme",
               url="https://x.com/1", location_raw=location_raw,
               hires_remotely_from=hires_remotely_from, description=description)


def test_location_worldwide_tier_a(prefs):
    res = classify_location(_job(location_raw="Remote - Worldwide"), prefs)
    assert res.tier == TIER_A and res.passed is True


def test_location_africa_tier_b(prefs):
    res = classify_location(_job(location_raw="Remote - Kenya, Nigeria, South Africa"), prefs)
    assert res.tier == TIER_B and res.passed is True


def test_location_us_only_tier_d_rejected(prefs):
    res = classify_location(_job(location_raw="Remote - US Only"), prefs)
    assert res.tier == TIER_D and res.passed is False


def test_location_restriction_buried_in_description_still_rejected(prefs):
    # location field just says "Remote" but the fine print restricts it -
    # this is exactly the false-negative case the brief warns about.
    res = classify_location(_job(location_raw="Remote", description="Must be located in the United States for this role."), prefs)
    assert res.passed is False


def test_location_unclear_tier_c_passes_to_ai(prefs):
    res = classify_location(_job(location_raw="Remote"), prefs)
    assert res.tier == TIER_C and res.passed is True


def test_location_explicit_field_overrides_vague_text(prefs):
    # Wellfound-style explicit field takes priority over generic "Remote" text.
    res = classify_location(_job(location_raw="Remote", hires_remotely_from="Worldwide"), prefs)
    assert res.tier == TIER_A


def test_location_explicit_country_list_excluding_africa_is_rejected(prefs):
    res = classify_location(_job(location_raw="Remote", hires_remotely_from="United States, Canada"), prefs)
    assert res.passed is False


# ---------- role ----------

def test_role_obvious_match_passes(prefs):
    assert check_role("Product Manager", prefs).passed is True


def test_role_excluded_keyword_rejected(prefs):
    assert check_role("Senior Backend Engineer", prefs).passed is False


def test_role_ambiguous_title_deferred_to_ai(prefs):
    # not on the include list, not excluded either - the brief wants these to
    # reach the AI rather than being silently dropped by a keyword list.
    res = check_role("Head of Client Delivery", prefs)
    assert res.passed is True


# ---------- full hard-filter pipeline: false-positive / false-negative style cases ----------

def test_pipeline_rejects_senior_us_only_eight_years(prefs):
    """A posting that should be an obvious reject on three independent grounds."""
    job = Job(source="s", external_id="1", title="Senior Product Manager", company="BigCo",
              url="https://x.com/1", location_raw="Remote - US Only",
              description="8+ years of experience required.")
    verdict = run_hard_filters(job, prefs)
    assert verdict.passed is False


def test_pipeline_passes_worldwide_junior_pm_to_ai(prefs):
    job = Job(source="s", external_id="1", title="Associate Product Manager", company="StartCo",
              url="https://x.com/1", location_raw="Remote - Anywhere",
              description="1-2 years of experience in a SaaS environment.")
    verdict = run_hard_filters(job, prefs)
    assert verdict.passed is True
    assert verdict.location_tier == TIER_A


def test_pipeline_passes_five_year_africa_role_flagged_for_realism(prefs):
    job = Job(source="s", external_id="1", title="Product Manager", company="EuroSaaS",
              url="https://x.com/1", location_raw="Remote - EMEA",
              description="5 years of B2B SaaS product management experience required.")
    verdict = run_hard_filters(job, prefs)
    assert verdict.passed is True
    assert verdict.needs_realism_check is True


def test_pipeline_rejects_missing_company_name(prefs):
    job = Job(source="s", external_id="1", title="Product Manager", company="",
              url="https://x.com/1", location_raw="Remote - Worldwide")
    verdict = run_hard_filters(job, prefs)
    assert verdict.passed is False
