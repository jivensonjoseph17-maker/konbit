"""
Konbit — Tès dat ak fizo orè nan schema yo
Chemen: backend/tests/test_schema_dates.py
"""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.schemas import InterviewCreate, OfferCreate


def test_interview_without_timezone_is_rejected():
    # Sa se egzakteman sa <input type="datetime-local"> voye
    with pytest.raises(ValidationError):
        InterviewCreate(application_id=1, scheduled_at="2026-10-01T10:00")


def test_interview_haiti_time_is_stored_as_utc():
    # 10è maten lè Ayiti (UTC-4 an oktòb) = 14è UTC
    iv = InterviewCreate(application_id=1, scheduled_at="2026-10-01T10:00:00-04:00")
    assert iv.scheduled_at == datetime(2026, 10, 1, 14, 0, tzinfo=timezone.utc)
    assert iv.scheduled_at.utcoffset() == timedelta(0)


def test_offer_expiry_without_timezone_is_rejected():
    with pytest.raises(ValidationError):
        OfferCreate(application_id=1, salary=100, expires_at="2026-10-15T17:00")


def test_offer_expiry_stays_optional():
    assert OfferCreate(application_id=1, salary=100).expires_at is None