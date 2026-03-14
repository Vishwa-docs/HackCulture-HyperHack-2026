"""Date parsing and validation."""
import re
from datetime import datetime, date
from typing import Optional, Tuple

# Common date formats in Indian financial documents
DATE_FORMATS = [
    "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
    "%d/%m/%y", "%d-%m-%y", "%d.%m.%y",
    "%Y-%m-%d", "%Y/%m/%d",
    "%d %b %Y", "%d %B %Y",
    "%d-%b-%Y", "%d-%B-%Y",
    "%b %d, %Y", "%B %d, %Y",
    "%d %b, %Y", "%d %B, %Y",
]

# Days per month (non-leap year)
DAYS_IN_MONTH = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                  7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}


def is_leap_year(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def max_days_in_month(month: int, year: int) -> int:
    if month == 2 and is_leap_year(year):
        return 29
    return DAYS_IN_MONTH.get(month, 31)


def parse_date(date_str: str) -> Optional[date]:
    """Try to parse a date string. Returns None if unparseable."""
    s = date_str.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def validate_date_string(date_str: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a date string. Returns (is_valid, reason).
    Detects impossible dates like Feb 31, Sep 31, etc.
    """
    s = date_str.strip()
    if not s:
        return True, None

    # Try to extract day/month/year components
    # Pattern: dd/mm/yyyy or dd-mm-yyyy or dd.mm.yyyy
    m = re.match(r'(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})', s)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000

        if month < 1 or month > 12:
            return False, f"Invalid month {month}"
        if day < 1:
            return False, f"Invalid day {day}"

        max_d = max_days_in_month(month, year)
        if day > max_d:
            return False, f"Day {day} exceeds max {max_d} for month {month}"
        return True, None

    # Pattern: yyyy-mm-dd
    m = re.match(r'(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})', s)
    if m:
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if month < 1 or month > 12:
            return False, f"Invalid month {month}"
        if day < 1:
            return False, f"Invalid day {day}"
        max_d = max_days_in_month(month, year)
        if day > max_d:
            return False, f"Day {day} exceeds max {max_d} for month {month}"
        return True, None

    # Try named months
    m = re.match(r'(\d{1,2})\s+(\w+)\s+(\d{2,4})', s)
    if m:
        day = int(m.group(1))
        month_name = m.group(2)
        year = int(m.group(3))
        if year < 100:
            year += 2000
        try:
            month = datetime.strptime(month_name, "%b").month
        except ValueError:
            try:
                month = datetime.strptime(month_name, "%B").month
            except ValueError:
                return True, None  # Can't parse month name, don't flag
        max_d = max_days_in_month(month, year)
        if day > max_d:
            return False, f"Day {day} exceeds max {max_d} for month {month}"
        return True, None

    return True, None


def normalize_date_to_iso(date_str: str) -> str:
    """Normalize date to ISO format. Returns original if unparseable."""
    d = parse_date(date_str)
    if d:
        return d.isoformat()
    return date_str
