from datetime import datetime, timedelta, timezone

import pytest

from celery.exceptions import CPendingDeprecationWarning
from celery.utils.iso8601 import parse_iso8601


def test_parse_iso8601_utc():
    dt = parse_iso8601("2023-10-26T10:30:00Z")
    assert dt == datetime(2023, 10, 26, 10, 30, 0, tzinfo=timezone.utc)


def test_parse_iso8601_positive_offset():
    dt = parse_iso8601("2023-10-26T10:30:00+05:30")
    expected_tz = timezone(timedelta(hours=5, minutes=30))
    assert dt == datetime(2023, 10, 26, 10, 30, 0, tzinfo=expected_tz)


def test_parse_iso8601_negative_offset():
    dt = parse_iso8601("2023-10-26T10:30:00-08:00")
    expected_tz = timezone(timedelta(hours=-8))
    assert dt == datetime(2023, 10, 26, 10, 30, 0, tzinfo=expected_tz)


def test_parse_iso8601_with_microseconds():
    dt = parse_iso8601("2023-10-26T10:30:00.123456Z")
    assert dt == datetime(2023, 10, 26, 10, 30, 0, 123456, tzinfo=timezone.utc)


def test_parse_iso8601_date_only():
    dt = parse_iso8601("2023-10-26")
    assert dt == datetime(2023, 10, 26, 0, 0, 0)  # Expects naive datetime


def test_parse_iso8601_date_hour_minute_only():
    # The regex uses '.' as a separator, often 'T' is used.
    # Let's test with 'T' as it's common in ISO8601.
    dt = parse_iso8601("2023-10-26T10:30")
    assert dt == datetime(2023, 10, 26, 10, 30, 0)  # Expects naive datetime


def test_parse_iso8601_invalid_string():
    with pytest.raises(ValueError, match="unable to parse date string"):
        parse_iso8601("invalid-date-string")


def test_parse_iso8601_malformed_strings():
    # These strings match the regex but have invalid date/time component values
    invalid_component_strings = [
        "2023-13-01T00:00:00Z",  # Invalid month
        "2023-12-32T00:00:00Z",  # Invalid day
        "2023-12-01T25:00:00Z",  # Invalid hour
        "2023-12-01T00:60:00Z",  # Invalid minute
        "2023-12-01T00:00:60Z",  # Invalid second
    ]
    for s in invalid_component_strings:
        # For these, the error comes from datetime constructor
        with pytest.raises(ValueError):
            parse_iso8601(s)

    # A timezone with non-digit characters in the offset no longer matches the
    # regex end-to-end, so the parser now raises ValueError instead of silently
    # stripping the bad timezone and returning a naive datetime.
    malformed_tz_string = "2023-10-26T10:30:00+05:AA"
    with pytest.raises(ValueError, match="unable to parse date string"):
        parse_iso8601(malformed_tz_string)

    # The compact "20231026T103000Z" form does not match the regex (which
    # requires '-' separators between the date components), so the parser
    # raises ValueError instead of crashing with TypeError from int(None).
    unparseable_string = "20231026T103000Z"
    with pytest.raises(ValueError, match="unable to parse date string"):
        parse_iso8601(unparseable_string)


@pytest.mark.parametrize(
    "datestring",
    [
        "2023-10-26T10:30:00garbage",
        "2023-10-26T10:30:00+05:00extra",
        "2023-10-26T10:30:00.123Ztrailing",
        "2023-10-26garbage",
        "2023-10-26T10:30junk",
        "2023-10-26T10:30:00+junk",
        "2023garbage",
        "2023-10garbage",
    ],
)
def test_parse_iso8601_rejects_trailing_garbage(datestring):
    # Previously the regex used re.match which only anchors at the start of
    # the string, so trailing characters after a valid ISO-8601 prefix were
    # silently dropped and the parser returned a datetime for the prefix.
    # Switching to fullmatch means the whole string must match the pattern.
    with pytest.raises(ValueError, match="unable to parse date string"):
        parse_iso8601(datestring)


def test_parse_iso8601_deprecation_warning():
    with pytest.warns(CPendingDeprecationWarning, match="parse_iso8601 is scheduled for deprecation"):
        parse_iso8601("2023-10-26T10:30:00Z")
