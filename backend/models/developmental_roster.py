"""Domain model for the NXT developmental roster pipeline."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict


@dataclass
class DevelopmentalProspect:
    prospect_id: str
    free_agent_id: str
    wrestler_name: str
    assigned_brand: str = "ROC NXT"
    stage: str = "trainee"
    readiness_score: float = 0.0
    promo_score: float = 0.0
    in_ring_score: float = 0.0
    consistency_score: float = 0.0
    momentum_score: float = 0.0
    projected_ceiling: str = "midcard"
    call_up_priority: float = 0.0
    assigned_main_brand: str = ""
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CallUpDecision:
    prospect_id: str
    wrestler_name: str
    target_brand: str
    confidence: float
    recommendation: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
