"""Call-up scoring engine for NXT to main roster transitions."""

from __future__ import annotations

from typing import Dict, Any


def calculate_call_up_priority(profile: Dict[str, Any]) -> float:
    """Calculate a weighted readiness score (0-100)."""
    readiness = float(profile.get("readiness_score", 0.0))
    promo = float(profile.get("promo_score", 0.0))
    in_ring = float(profile.get("in_ring_score", 0.0))
    consistency = float(profile.get("consistency_score", 0.0))
    momentum = float(profile.get("momentum_score", 0.0))

    raw = (
        readiness * 0.32
        + promo * 0.16
        + in_ring * 0.27
        + consistency * 0.15
        + momentum * 0.10
    )
    return max(0.0, min(100.0, round(raw, 2)))


def build_call_up_recommendation(priority: float) -> str:
    if priority >= 85:
        return "Immediate call-up"
    if priority >= 72:
        return "Call-up within 1-2 months"
    if priority >= 60:
        return "Keep on NXT TV, reassess quarterly"
    return "Continue developmental training"
