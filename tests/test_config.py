from datetime import datetime, timezone, timedelta
from src.config import kst_now, session_label, size_class


def test_kst_now_is_kst_offset():
    now = kst_now()
    assert now.utcoffset() == timedelta(hours=9)


def test_session_label_am_pm():
    kst = timezone(timedelta(hours=9))
    d10 = datetime(2026, 7, 3, 10, 0, tzinfo=kst)
    d18 = datetime(2026, 7, 3, 18, 0, tzinfo=kst)
    assert session_label(d10) == "AM 10시"
    assert session_label(d18) == "PM 6시"


def test_session_label_from_utc_input():
    """Cron runs UTC. Ensure we translate to KST before labeling."""
    utc = timezone.utc
    kst_10 = datetime(2026, 7, 3, 1, 0, tzinfo=utc)   # UTC 01:00 = KST 10:00
    kst_18 = datetime(2026, 7, 3, 9, 0, tzinfo=utc)   # UTC 09:00 = KST 18:00
    assert session_label(kst_10) == "AM 10시"
    assert session_label(kst_18) == "PM 6시"


def test_size_class_tiers():
    assert size_class(0) == 1
    assert size_class(10) == 1
    assert size_class(11) == 2
    assert size_class(20) == 2
    assert size_class(21) == 3
    assert size_class(31) == 4
