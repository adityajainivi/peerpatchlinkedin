import pytest

from peerpatch_linkedin.filters import is_hiring_post, mentions_title


@pytest.mark.parametrize("text", [
    "We're hiring a Data Analyst in Bengaluru!",
    "We’re Hiring! Data Analyst, 2+ yrs",  # curly apostrophe
    "#NowHiring data analysts for our Pune office",
    "Job openings for analysts. Apply now.",
    "Openings for freshers in Gurugram",
    "We have 3 vacancies in the analytics team",
    "Looking for a Data Analyst to join my team. DM me.",
    "Please share your updated CV at jobs@acme.in",
    "Referrals welcome for this role",
    "Walk-in drive this Saturday, immediate joiners preferred",
    "Open positions in our data team",
])
def test_hiring_posts_are_kept(text):
    assert is_hiring_post(text)


@pytest.mark.parametrize("text", [
    "I'm looking for a new role as a Data Analyst. #OpenToWork",
    "I am actively seeking full-time opportunities. Hiring managers, DM me!",
    "Open to work: data analyst, 2 years SQL. Referrals appreciated.",
    "Im looking for a job in analytics, any referrals?",
    "I am an immediate joiner, please share openings",
])
def test_job_seeker_posts_are_dropped(text):
    assert not is_hiring_post(text)


@pytest.mark.parametrize("text", [
    "Five SQL tricks every data analyst should know",
    "What an eye-opening conference",
    "",
])
def test_posts_without_hiring_language_are_dropped(text):
    assert not is_hiring_post(text)


@pytest.mark.parametrize("text, title, expected", [
    ("Hiring Data Analysts in Pune", "data analyst", True),
    ("Hiring analysts in Pune", "data analyst", False),
    ("We need a C++ developer", "C++ developer", True),
    ("She said the engineer left", "AI engineer", False),
    ("Hiring an AI engineer", "AI engineer", True),
    ("anything", "", False),
])
def test_mentions_title(text, title, expected):
    assert mentions_title(text, title) is expected
