"""Tests for date-related detectors."""
import pytest
from src.normalization.dates import validate_date_string, is_leap_year, max_days_in_month


class TestLeapYear:
    def test_2024_leap(self):
        assert is_leap_year(2024)

    def test_2025_not_leap(self):
        assert not is_leap_year(2025)

    def test_2000_leap(self):
        assert is_leap_year(2000)

    def test_1900_not_leap(self):
        assert not is_leap_year(1900)


class TestMaxDays:
    def test_jan(self):
        assert max_days_in_month(1, 2025) == 31

    def test_feb_non_leap(self):
        assert max_days_in_month(2, 2025) == 28

    def test_feb_leap(self):
        assert max_days_in_month(2, 2024) == 29

    def test_apr(self):
        assert max_days_in_month(4, 2025) == 30

    def test_sep(self):
        assert max_days_in_month(9, 2025) == 30


class TestDateValidation:
    def test_impossible_feb_30(self):
        is_valid, reason = validate_date_string("30/02/2025")
        assert not is_valid
        assert "max" in reason.lower() or "exceed" in reason.lower()

    def test_impossible_apr_31(self):
        is_valid, reason = validate_date_string("31/04/2025")
        assert not is_valid

    def test_impossible_jun_31(self):
        is_valid, reason = validate_date_string("31/06/2025")
        assert not is_valid

    def test_valid_jan_31(self):
        is_valid, _ = validate_date_string("31/01/2025")
        assert is_valid

    def test_valid_mar_31(self):
        is_valid, _ = validate_date_string("31/03/2025")
        assert is_valid
