"""
data_loader.py — CSV loading, validation, indexing for Buy or Wait?
"""
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from config import (
    REQUESTS_CSV, SAMPLE_REQUESTS_CSV, FINANCIAL_PROFILES_CSV,
    FINANCIAL_EVENTS_CSV, EXCHANGE_RATES_CSV, PAYMENT_OPTIONS_CSV,
    MESSAGES_CSV, IMAGES_CSV,
)
from models import (
    Request, FinancialProfile, FinancialEvent, ExchangeRate,
    PaymentOption, Message, ImageRecord,
)


def _parse_date(s: str) -> Optional[date]:
    s = s.strip()
    if not s:
        return None
    return date.fromisoformat(s)


def _parse_decimal(s: str) -> Optional[Decimal]:
    s = s.strip()
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _parse_bool(s: str) -> bool:
    return s.strip().lower() in ("true", "1", "yes")


def _parse_list(s: str) -> List[str]:
    s = s.strip()
    if not s:
        return []
    return [x.strip() for x in s.split("|") if x.strip()]


def _parse_int(s: str) -> Optional[int]:
    s = s.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def load_requests(path=None) -> List[Request]:
    path = path or REQUESTS_CSV
    requests = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            requests.append(Request(
                request_id=row["request_id"].strip(),
                user_id=row["user_id"].strip(),
                request_date=_parse_date(row["request_date"]),
                request_type=row["request_type"].strip(),
                requested_amount=Decimal(row["requested_amount"].strip()),
                desired_completion_date=_parse_date(row["desired_completion_date"]),
                allows_partial_payment=_parse_bool(row["allows_partial_payment"]),
                request_text=row["request_text"].strip(),
            ))
    return requests


def load_profiles() -> Dict[str, FinancialProfile]:
    profiles = {}
    with open(FINANCIAL_PROFILES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            uid = row["user_id"].strip()
            profiles[uid] = FinancialProfile(
                user_id=uid,
                home_currency=row["home_currency"].strip(),
                current_available_balance=Decimal(row["current_available_balance"].strip()),
                minimum_balance_to_keep=Decimal(row["minimum_balance_to_keep"].strip()),
                financial_priorities=_parse_list(row["financial_priorities"]),
                expense_categories_to_protect=_parse_list(row["expense_categories_to_protect"]),
                expense_categories_to_reduce=_parse_list(row["expense_categories_user_is_willing_to_reduce"]),
                expense_categories_to_stop=_parse_list(row["expense_categories_user_is_willing_to_stop"]),
                payment_methods_user_will_consider=_parse_list(row["payment_methods_user_will_consider"]),
                max_installment_months=_parse_int(row["max_installment_months"]),
            )
    return profiles


def load_events() -> Tuple[List[FinancialEvent], Dict[str, List[FinancialEvent]], Dict[str, FinancialEvent]]:
    """Returns (all_events, events_by_user, events_by_id)."""
    all_events = []
    events_by_user: Dict[str, List[FinancialEvent]] = defaultdict(list)
    events_by_id: Dict[str, FinancialEvent] = {}

    with open(FINANCIAL_EVENTS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            evt = FinancialEvent(
                event_id=row["event_id"].strip(),
                user_id=row["user_id"].strip(),
                event_type=row["event_type"].strip(),
                description=row["description"].strip(),
                category=row["category"].strip(),
                direction=row["direction"].strip(),
                amount=_parse_decimal(row["amount"]),
                currency=row["currency"].strip(),
                event_date=_parse_date(row["event_date"]),
                settlement_date=_parse_date(row["settlement_date"]),
                status=row["status"].strip(),
                linked_event_id=row["linked_event_id"].strip(),
                flexibility=row["flexibility"].strip(),
                minimum_allowed_amount=_parse_decimal(row["minimum_allowed_amount"]),
            )
            all_events.append(evt)
            events_by_user[evt.user_id].append(evt)
            events_by_id[evt.event_id] = evt

    return all_events, dict(events_by_user), events_by_id


def load_exchange_rates() -> List[ExchangeRate]:
    rates = []
    with open(EXCHANGE_RATES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rates.append(ExchangeRate(
                rate_date=_parse_date(row["rate_date"]),
                from_currency=row["from_currency"].strip(),
                to_currency=row["to_currency"].strip(),
                rate=Decimal(row["rate"].strip()),
            ))
    return sorted(rates, key=lambda r: r.rate_date)


def load_payment_options() -> Dict[str, List[PaymentOption]]:
    """Returns options_by_request_id."""
    options_by_request: Dict[str, List[PaymentOption]] = defaultdict(list)
    with open(PAYMENT_OPTIONS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            opt = PaymentOption(
                payment_option_id=row["payment_option_id"].strip(),
                request_id=row["request_id"].strip(),
                payment_method=row["payment_method"].strip(),
                payment_amount=Decimal(row["payment_amount"].strip()),
                number_of_payments=int(row["number_of_payments"].strip()),
                first_payment_date=_parse_date(row["first_payment_date"]),
                payment_frequency_days=_parse_int(row["payment_frequency_days"]),
                financing_fee=Decimal(row["financing_fee"].strip()),
                total_payable_amount=Decimal(row["total_payable_amount"].strip()),
            )
            options_by_request[opt.request_id].append(opt)
    return dict(options_by_request)


def load_messages() -> Tuple[List[Message], Dict[str, List[Message]], Dict[str, List[Message]], Dict[str, List[Message]]]:
    """Returns (all_messages, messages_by_user, messages_by_request, messages_by_event)."""
    all_messages = []
    by_user: Dict[str, List[Message]] = defaultdict(list)
    by_request: Dict[str, List[Message]] = defaultdict(list)
    by_event: Dict[str, List[Message]] = defaultdict(list)

    with open(MESSAGES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # Parse sent_at: ISO timestamp
            sent_str = row["sent_at"].strip()
            try:
                sent_at = datetime.fromisoformat(sent_str.replace("Z", "+00:00"))
            except Exception:
                sent_at = datetime.min

            msg = Message(
                message_id=row["message_id"].strip(),
                user_id=row["user_id"].strip(),
                request_id=row["request_id"].strip(),
                related_event_id=row["related_event_id"].strip(),
                sent_at=sent_at,
                source_type=row["source_type"].strip(),
                message_text=row["message_text"].strip(),
            )
            all_messages.append(msg)
            by_user[msg.user_id].append(msg)
            if msg.request_id:
                by_request[msg.request_id].append(msg)
            if msg.related_event_id:
                by_event[msg.related_event_id].append(msg)

    return all_messages, dict(by_user), dict(by_request), dict(by_event)


def load_images() -> Tuple[List[ImageRecord], Dict[str, ImageRecord], Dict[str, ImageRecord]]:
    """Returns (all_images, images_by_event, images_by_request)."""
    all_images = []
    by_event: Dict[str, ImageRecord] = {}
    by_request: Dict[str, List[ImageRecord]] = defaultdict(list)

    with open(IMAGES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            img = ImageRecord(
                image_id=row["image_id"].strip(),
                user_id=row["user_id"].strip(),
                request_id=row["request_id"].strip(),
                related_event_id=row["related_event_id"].strip(),
            )
            all_images.append(img)
            if img.related_event_id:
                by_event[img.related_event_id] = img
            if img.request_id:
                by_request[img.request_id].append(img)

    return all_images, by_event, dict(by_request)
