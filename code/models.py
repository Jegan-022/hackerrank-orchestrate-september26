"""
models.py — Typed dataclasses for all entities in Buy or Wait?
"""
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List, Dict


@dataclass
class FinancialProfile:
    user_id: str
    home_currency: str
    current_available_balance: Decimal
    minimum_balance_to_keep: Decimal
    financial_priorities: List[str]           # pipe-separated in CSV
    expense_categories_to_protect: List[str]  # pipe-separated
    expense_categories_to_reduce: List[str]   # pipe-separated
    expense_categories_to_stop: List[str]     # pipe-separated
    payment_methods_user_will_consider: List[str]  # pipe-separated
    max_installment_months: Optional[int]     # blank = no installments


@dataclass
class FinancialEvent:
    event_id: str
    user_id: str
    event_type: str
    description: str
    category: str
    direction: str         # credit | debit | non_cash
    amount: Optional[Decimal]   # None if blank
    currency: str
    event_date: date
    settlement_date: Optional[date]
    status: str            # settled | pending | scheduled | cancelled | failed | unrealized
    linked_event_id: str   # empty string if none
    flexibility: str       # fixed | reducible | stoppable | reducible_or_stoppable
    minimum_allowed_amount: Optional[Decimal]
    # Derived fields
    amount_in_home_currency: Optional[Decimal] = None  # filled after FX conversion
    is_resolved: bool = False          # filled after event resolution


@dataclass
class ExchangeRate:
    rate_date: date
    from_currency: str
    to_currency: str
    rate: Decimal


@dataclass
class PaymentOption:
    payment_option_id: str
    request_id: str
    payment_method: str         # full_payment | installments
    payment_amount: Decimal
    number_of_payments: int
    first_payment_date: date
    payment_frequency_days: Optional[int]
    financing_fee: Decimal
    total_payable_amount: Decimal


@dataclass
class Request:
    request_id: str
    user_id: str
    request_date: date
    request_type: str
    requested_amount: Decimal
    desired_completion_date: date
    allows_partial_payment: bool
    request_text: str


@dataclass
class Message:
    message_id: str
    user_id: str
    request_id: str         # may be empty
    related_event_id: str   # may be empty
    sent_at: datetime
    source_type: str
    message_text: str
    # Parsed interpretation (filled by message_parser)
    action: str = "NONE"    # NONE | AMEND | CANCEL | DELAY | CONFIRM | SETTLE
    parsed_event_id: str = ""
    new_amount: Optional[Decimal] = None
    new_date: Optional[date] = None
    parse_currency: str = ""
    parse_confidence: float = 0.0


@dataclass
class ImageRecord:
    image_id: str
    user_id: str
    request_id: str
    related_event_id: str
    # Extracted fields (filled by image_extractor)
    extracted_amount: Optional[Decimal] = None
    extracted_currency: str = ""
    extracted_date: Optional[date] = None
    extraction_confidence: float = 0.0


@dataclass
class PaymentEntry:
    """Single payment within a plan."""
    date: date
    amount: Decimal


@dataclass
class Plan:
    """A candidate payment plan."""
    method: str                        # full_payment | partial_payment | installments | wait | not_recommended
    payments: List[PaymentEntry]       # sorted chronologically
    total_payable: Decimal
    spending_changes: List[str]        # stop:event_id | reduce_to:event_id:amount
    payment_option_id: str             # for installments, else ""
    completes_by_deadline: bool
    requires_spending_changes: bool


@dataclass
class OutputRow:
    request_id: str
    amount_safe_to_pay: Decimal
    affordability_status: str
    recommended_payment_method: str
    payment_plan: str              # pipe-joined YYYY-MM-DD:amount or "none"
    earliest_date_for_full_payment: str   # YYYY-MM-DD or ""
    spending_changes_needed: str   # pipe-joined or "none"
    decision_explanation: str
