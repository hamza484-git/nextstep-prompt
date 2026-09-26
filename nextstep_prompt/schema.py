"""Shared response schema. Deliberately kept in sync with the Agent repo's shape.

The Prompt-Engineer role owns THIS file; the Agent consumes it via the mock API.
If the two ever drift, this one is authoritative.
"""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class RiskFlag(str, Enum):
    AT_RISK_EMOTIONAL = "at_risk_emotional"
    PROMPT_INJECTION = "prompt_injection"
    HARMFUL_REQUEST = "harmful_request"
    CONTRADICTION = "contradiction"
    WORSE_AFTER_ACTION = "worse_after_action"
    OFF_TOPIC = "off_topic"
    MISSING_INFO = "missing_info"


class Priority(BaseModel):
    id: str
    title: str
    why: str
    action: Optional[str] = None
    rank: int
    tied_with: list[str] = Field(default_factory=list)
    confidence: float


class Assessment(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    situation_id: str
    version: int = 1
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str
    urgency: Literal["low", "medium", "high", "immediate"]
    constraints: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    priorities: list[Priority] = Field(default_factory=list)
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    uncertainty: float
    calm_mode: bool = False
    recovery_mode: bool = False
    notes_to_user: Optional[str] = None
