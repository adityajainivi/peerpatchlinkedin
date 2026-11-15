from datetime import datetime, timezone

import pytest

from peerpatch_linkedin.timeparse import relative_label_to_hours, urn_to_datetime
from tests.linkedin_markup import urn_for

WHEN = datetime(2026, 11, 14, 9, 30, 15, 123000, tzinfo=timezone.utc)


@pytest.mark.parametrize("kind", ["activity", "ugcPost", "share"])
def test_post_id_decodes_to_exact_creation_time(kind):
    assert urn_to_datetime(urn_for(WHEN, kind)) == WHEN


def test_urn_inside_a_link_still_decodes():
    link = f"https://www.linkedin.com/feed/update/{urn_for(WHEN)}/?utm_source=share"
    assert urn_to_datetime(link) == WHEN


@pytest.mark.parametrize("bad", ["", "urn:li:activity:12345", "urn:li:comment:7392847561234567890", "nonsense"])
def test_ids_without_a_usable_time_give_none(bad):
    assert urn_to_datetime(bad) is None


@pytest.mark.parametrize("label, hours", [
    ("now", 0.0), ("Just now", 0.0), ("45s", 45 / 3600), ("5m", 5 / 60), ("3h", 3.0),
    ("1d • Edited •", 24.0), ("2w", 336.0), ("3mo", 2160.0), ("1yr", 8760.0),
    ("23 hours ago", 23.0), ("1 day ago • Edited", 24.0), ("2 weeks ago", 336.0),
])
def test_relative_labels(label, hours):
    assert relative_label_to_hours(label) == pytest.approx(hours)


@pytest.mark.parametrize("label", ["", "Promoted", "Edited"])
def test_unreadable_labels_give_none(label):
    assert relative_label_to_hours(label) is None
