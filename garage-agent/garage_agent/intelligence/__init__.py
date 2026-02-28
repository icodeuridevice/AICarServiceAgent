"""Deterministic intelligence layer for workshop analytics."""

from garage_agent.intelligence.customer_health import update_customer_health
from garage_agent.intelligence.issue_detection import detect_repeated_issue
from garage_agent.intelligence.service_prediction import (
    calculate_next_service,
    get_due_vehicles,
)
from garage_agent.intelligence.upsell_engine import suggest_upsell_services

__all__ = [
    "calculate_next_service",
    "detect_repeated_issue",
    "get_due_vehicles",
    "suggest_upsell_services",
    "update_customer_health",
]
