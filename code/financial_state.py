"""
financial_state.py — Per-user financial state reconstruction.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from models import (
    FinancialProfile, FinancialEvent, ExchangeRate,
    Message, ImageRecord,
)
from event_resolver import (
    resolve_events, get_cash_flow_events, detect_recurring_events,
)
from currency import CurrencyConverter
from image_extractor import extract_from_image
from message_parser import parse_messages_for_user


class FinancialState:
    """
    Reconstructed financial state for one user.
    Built once, reused across all requests for that user.
    """

    def __init__(
        self,
        profile: FinancialProfile,
        events: List[FinancialEvent],
        events_by_id: Dict[str, FinancialEvent],
        messages: List[Message],
        images_by_event: Dict[str, ImageRecord],
        converter: CurrencyConverter,
    ):
        self.profile = profile
        self.converter = converter
        self.user_id = profile.user_id
        self.home_currency = profile.home_currency
        self.current_balance = profile.current_available_balance
        self.minimum_balance = profile.minimum_balance_to_keep

        # 1. Fill blank amounts from images
        self._fill_blank_amounts(events, images_by_event)

        # 2. Convert all event amounts to home currency
        self._convert_to_home_currency(events)

        # 3. Resolve linked event chains
        self.resolved_events = resolve_events(events_by_id, events)

        # 4. Get cash flow events (status-filtered)
        self.cash_flow_events = get_cash_flow_events(self.resolved_events)

        # 5. Parse messages
        self.parsed_messages = parse_messages_for_user(messages)

        # Apply message amendments to events
        self._apply_message_amendments(events_by_id)

        # 6. Separate events into categories for easy access
        self._categorize_events()

    def _fill_blank_amounts(
        self,
        events: List[FinancialEvent],
        images_by_event: Dict[str, ImageRecord],
    ) -> None:
        """Fill blank event amounts from linked images."""
        for ev in events:
            if ev.amount is not None:
                continue
            # Look for image
            img_record = images_by_event.get(ev.event_id)
            if img_record is None:
                # No image — leave amount as None (handled conservatively)
                print(f"  [financial_state] No image for blank amount event {ev.event_id}")
                continue

            extraction = extract_from_image(img_record.image_id)
            if extraction["amount"] is not None:
                ev.amount = extraction["amount"]
                # If extracted currency differs, store it
                if extraction["currency"] and extraction["currency"] != ev.currency:
                    ev.currency = extraction["currency"]
                print(f"  [financial_state] Extracted amount for {ev.event_id}: "
                      f"{ev.amount} {ev.currency} (confidence={extraction['confidence']:.2f})")
            else:
                print(f"  [financial_state] Could not extract amount for {ev.event_id}")

    def _convert_to_home_currency(self, events: List[FinancialEvent]) -> None:
        """Convert all event amounts to home currency."""
        for ev in events:
            if ev.amount is None:
                ev.amount_in_home_currency = None
                continue
            if ev.currency == self.home_currency:
                ev.amount_in_home_currency = ev.amount
            else:
                use_date = ev.settlement_date or ev.event_date
                converted = self.converter.convert(
                    ev.amount, ev.currency, self.home_currency, use_date
                )
                ev.amount_in_home_currency = converted
                if converted is None:
                    print(f"  [financial_state] Cannot convert {ev.currency}->{self.home_currency} "
                          f"for {ev.event_id} on {use_date}")

    def _apply_message_amendments(self, events_by_id: Dict[str, FinancialEvent]) -> None:
        """Apply parsed message amendments to relevant events."""
        for msg in self.parsed_messages:
            if msg.action == "NONE" or msg.parse_confidence < 0.6:
                continue
            if not msg.related_event_id:
                continue

            ev = events_by_id.get(msg.related_event_id)
            if ev is None:
                continue

            if msg.action == "CANCEL":
                ev.status = "cancelled"
            elif msg.action in ("AMEND", "SETTLE") and msg.new_amount is not None:
                old_amount = ev.amount
                ev.amount = msg.new_amount
                if msg.parse_currency:
                    ev.currency = msg.parse_currency
                # Reconvert
                use_date = ev.settlement_date or ev.event_date
                if ev.currency == self.home_currency:
                    ev.amount_in_home_currency = ev.amount
                else:
                    converted = self.converter.convert(
                        ev.amount, ev.currency, self.home_currency, use_date
                    )
                    ev.amount_in_home_currency = converted
                print(f"  [financial_state] Amended event {ev.event_id}: "
                      f"{old_amount} -> {ev.amount} {ev.currency}")
            elif msg.action == "DELAY" and msg.new_date is not None:
                ev.event_date = msg.new_date
                if ev.settlement_date:
                    ev.settlement_date = msg.new_date

    def _categorize_events(self) -> None:
        """Categorize cash flow events by type for easy forecasting."""
        self.scheduled_debits: List[FinancialEvent] = []
        self.scheduled_credits: List[FinancialEvent] = []
        self.pending_debits: List[FinancialEvent] = []

        for ev in self.cash_flow_events:
            if ev.status == "pending" and ev.direction == "debit":
                self.pending_debits.append(ev)
            elif ev.status in ("scheduled",) and ev.direction == "debit":
                self.scheduled_debits.append(ev)
            elif ev.status in ("scheduled",) and ev.direction == "credit":
                self.scheduled_credits.append(ev)


def build_financial_states(
    profiles: Dict[str, FinancialProfile],
    events_by_user: Dict[str, List[FinancialEvent]],
    events_by_id: Dict[str, FinancialEvent],
    messages_by_user: Dict[str, List[Message]],
    images_by_event: Dict[str, ImageRecord],
    converter: CurrencyConverter,
) -> Dict[str, FinancialState]:
    """Build financial states for all users that have requests."""
    states = {}
    for user_id, profile in profiles.items():
        user_events = events_by_user.get(user_id, [])
        user_messages = messages_by_user.get(user_id, [])
        state = FinancialState(
            profile=profile,
            events=user_events,
            events_by_id=events_by_id,
            messages=user_messages,
            images_by_event=images_by_event,
            converter=converter,
        )
        states[user_id] = state
    return states
