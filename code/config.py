"""
config.py — Central configuration for Buy or Wait? engine.
"""
import os
from pathlib import Path

# Repository root (parent of code/)
REPO_ROOT = Path(__file__).parent.parent
DATASET_DIR = REPO_ROOT / "dataset"
MEDIA_DIR = DATASET_DIR / "media" / "images"
OUTPUT_PATH = REPO_ROOT / "output.csv"
LOG_PATH = REPO_ROOT / "log.txt"
CACHE_DIR = REPO_ROOT / "cache"

# Dataset files
REQUESTS_CSV = DATASET_DIR / "requests.csv"
SAMPLE_REQUESTS_CSV = DATASET_DIR / "sample_requests.csv"
FINANCIAL_PROFILES_CSV = DATASET_DIR / "financial_profiles.csv"
FINANCIAL_EVENTS_CSV = DATASET_DIR / "financial_events.csv"
EXCHANGE_RATES_CSV = DATASET_DIR / "exchange_rates.csv"
PAYMENT_OPTIONS_CSV = DATASET_DIR / "request_payment_options.csv"
MESSAGES_CSV = DATASET_DIR / "messages.csv"
IMAGES_CSV = DATASET_DIR / "images.csv"

# Forecast horizon
FORECAST_DAYS = 90

# LLM configuration (from environment)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "gemini-2.0-flash")
LLM_TEMPERATURE = 0

# Prompt version for cache invalidation
IMAGE_PROMPT_VERSION = "v1"
MESSAGE_PROMPT_VERSION = "v1"
EXPLANATION_PROMPT_VERSION = "v1"

# Output columns (exact order required)
OUTPUT_COLUMNS = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]

# Valid enum values
VALID_AFFORDABILITY_STATUS = {
    "affordable_now",
    "affordable_with_plan",
    "affordable_later",
    "not_affordable",
}

VALID_PAYMENT_METHODS = {
    "full_payment",
    "partial_payment",
    "installments",
    "wait",
    "not_recommended",
}

# Flexibility values that permit spending changes
STOPPABLE_FLEXIBILITY = {"stoppable", "reducible_or_stoppable"}
REDUCIBLE_FLEXIBILITY = {"reducible", "reducible_or_stoppable"}
