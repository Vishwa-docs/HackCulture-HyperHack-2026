"""Money/currency normalization using Decimal."""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional


def parse_money(val) -> Optional[Decimal]:
    """Parse a currency string to Decimal."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, float)):
        return Decimal(str(val))
    s = str(val).strip()
    s = re.sub(r'[₹$€£\s]', '', s)
    s = s.replace(',', '')
    # Handle parenthetical negatives
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]
    if not s or s == '-':
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def format_money(val: Optional[Decimal], places: int = 2) -> str:
    """Format Decimal to string with specified decimal places."""
    if val is None:
        return ""
    quantize_str = '0.' + '0' * places
    return str(val.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP))


def money_equal(a: Optional[Decimal], b: Optional[Decimal], tolerance: Decimal = Decimal("0.01")) -> bool:
    """Check if two money values are equal within tolerance."""
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= tolerance
