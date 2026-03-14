"""Tests for normalization modules."""
import pytest
from decimal import Decimal
from src.normalization.dates import validate_date_string, parse_date, normalize_date_to_iso
from src.normalization.money import parse_money, format_money, money_equal
from src.normalization.ids import normalize_invoice_number, normalize_po_number
from src.normalization.vendors import normalize_vendor_name, make_matching_key


class TestDateValidation:
    def test_valid_date(self):
        assert validate_date_string("15/03/2025") == (True, None)

    def test_valid_feb_28(self):
        assert validate_date_string("28/02/2025") == (True, None)

    def test_valid_feb_29_leap(self):
        assert validate_date_string("29/02/2024") == (True, None)

    def test_invalid_feb_29_non_leap(self):
        is_valid, reason = validate_date_string("29/02/2025")
        assert not is_valid

    def test_invalid_feb_31(self):
        is_valid, reason = validate_date_string("31/02/2025")
        assert not is_valid

    def test_invalid_sep_31(self):
        is_valid, reason = validate_date_string("31/09/2025")
        assert not is_valid

    def test_invalid_day_32(self):
        is_valid, reason = validate_date_string("32/01/2025")
        assert not is_valid

    def test_parse_dd_mm_yyyy(self):
        d = parse_date("15/03/2025")
        assert d is not None
        assert d.day == 15
        assert d.month == 3
        assert d.year == 2025

    def test_normalize_iso(self):
        assert normalize_date_to_iso("15/03/2025") == "2025-03-15"


class TestMoneyParsing:
    def test_plain_number(self):
        assert parse_money("1234.56") == Decimal("1234.56")

    def test_with_commas(self):
        assert parse_money("1,234.56") == Decimal("1234.56")

    def test_with_rupee_symbol(self):
        assert parse_money("₹1,234.56") == Decimal("1234.56")

    def test_with_dollar(self):
        assert parse_money("$1234") == Decimal("1234")

    def test_none(self):
        assert parse_money(None) is None

    def test_empty_string(self):
        assert parse_money("") is None

    def test_format(self):
        assert format_money(Decimal("1234.5")) == "1234.50"

    def test_money_equal_within_tolerance(self):
        assert money_equal(Decimal("100.00"), Decimal("100.005"))

    def test_money_not_equal(self):
        assert not money_equal(Decimal("100.00"), Decimal("100.05"))


class TestIDNormalization:
    def test_invoice_number(self):
        assert normalize_invoice_number("INV-2025-0042") == "INV-2025-42"

    def test_po_number(self):
        assert normalize_po_number("PO-2025-0001") == "PO-2025-1"

    def test_whitespace(self):
        assert normalize_invoice_number("  INV-2025-0042  ") == "INV-2025-42"


class TestVendorNormalization:
    def test_pvt_ltd(self):
        assert "Pvt Ltd" in normalize_vendor_name("Test Private Limited")

    def test_matching_key(self):
        key = make_matching_key("Test Pvt. Ltd.")
        assert "test" in key
        assert key.islower() or key.replace(" ", "").isalnum()
