"""
currency.py — Date-aware exchange rate lookup with binary search.
"""
from datetime import date
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import bisect

from models import ExchangeRate


class CurrencyConverter:
    """
    Converts amounts between currencies using historical exchange rates.
    Uses the most recent rate where rate_date <= event_date.
    NEVER uses a future exchange rate.
    """

    def __init__(self, rates: List[ExchangeRate]):
        # Build index: (from_currency, to_currency) -> sorted list of (date, rate)
        self._index: Dict[Tuple[str, str], List[Tuple[date, Decimal]]] = {}
        for r in sorted(rates, key=lambda x: x.rate_date):
            key = (r.from_currency, r.to_currency)
            if key not in self._index:
                self._index[key] = []
            self._index[key].append((r.rate_date, r.rate))

        # Also build reverse index for inverse lookups
        # We'll compute inverses on demand

    def get_rate(self, from_currency: str, to_currency: str, on_date: date) -> Optional[Decimal]:
        """
        Get exchange rate from_currency -> to_currency applicable on on_date.
        Returns the rate from the most recent entry where rate_date <= on_date.
        Returns None if no suitable rate exists.
        """
        if from_currency == to_currency:
            return Decimal("1")

        key = (from_currency, to_currency)
        if key in self._index:
            entries = self._index[key]
            # Binary search for latest entry with date <= on_date
            dates = [e[0] for e in entries]
            pos = bisect.bisect_right(dates, on_date) - 1
            if pos >= 0:
                return entries[pos][1]

        # Try inverse: to_currency -> from_currency then invert
        inv_key = (to_currency, from_currency)
        if inv_key in self._index:
            entries = self._index[inv_key]
            dates = [e[0] for e in entries]
            pos = bisect.bisect_right(dates, on_date) - 1
            if pos >= 0:
                inv_rate = entries[pos][1]
                if inv_rate != 0:
                    return Decimal("1") / inv_rate

        # Try via USD as bridge currency
        # from -> USD -> to
        if from_currency != "USD" and to_currency != "USD":
            rate_from_usd = self.get_rate("USD", from_currency, on_date)
            rate_to_usd = self.get_rate("USD", to_currency, on_date)
            if rate_from_usd and rate_to_usd and rate_from_usd != 0:
                return rate_to_usd / rate_from_usd

        return None

    def convert(
        self,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        on_date: date,
    ) -> Optional[Decimal]:
        """Convert amount from from_currency to to_currency using rate on on_date."""
        if from_currency == to_currency:
            return amount
        rate = self.get_rate(from_currency, to_currency, on_date)
        if rate is None:
            return None
        return amount * rate
