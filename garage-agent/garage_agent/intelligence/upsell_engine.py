"""Deterministic upsell recommendation helpers."""

from typing import Final

from sqlalchemy.orm import Session

from garage_agent.intelligence.issue_detection import detect_repeated_issue

DEFAULT_UPSELLS: Final[tuple[str, ...]] = (
    "wheel_alignment",
    "car_wash",
)
SERVICE_UPSELLS: Final[dict[str, tuple[str, ...]]] = {
    "oil_change": ("engine_flush", "air_filter_replacement"),
    "general_service": ("wheel_alignment", "ac_filter_replacement"),
    "full_service": ("detailing", "battery_health_check"),
}
REPEATED_ISSUE_UPSELL: Final[str] = "comprehensive_diagnostics"


def suggest_upsell_services(
    db: Session,
    garage_id: int,
    vehicle_id: int,
    service_type: str,
) -> list[str]:
    """Return deterministic upsell suggestions for a service interaction."""
    normalized_service_type = service_type.strip().lower()
    suggestions = list(SERVICE_UPSELLS.get(normalized_service_type, DEFAULT_UPSELLS))

    if detect_repeated_issue(
        db=db,
        garage_id=garage_id,
        vehicle_id=vehicle_id,
        service_type=service_type,
    ):
        if REPEATED_ISSUE_UPSELL not in suggestions:
            suggestions.insert(0, REPEATED_ISSUE_UPSELL)

    return suggestions
