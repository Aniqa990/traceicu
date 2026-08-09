from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models import Evidence


class AskRequest(BaseModel):
    subject_id: int
    question: str
    # Optional overrides. If omitted, the most recent admission / ICU
    # stay for the patient is used (see resolve_scope in retrieval.py).
    hadm_id: Optional[int] = None
    stay_id: Optional[int] = None


class QueryPlan(BaseModel):
    """The structured plan the LLM produced, echoed back for transparency."""

    intent: str
    domain: Optional[str] = None
    concept: Optional[str] = None
    time_scope: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    hadm_id: Optional[int] = None
    stay_id: Optional[int] = None


class AskResponse(BaseModel):
    status: Literal["supported", "abstain", "out_of_scope"]
    answer: str

    evidence: list[Evidence] = Field(default_factory=list)
    evidence_coverage: float  # 1.0 if every claim in `answer` is backed by `evidence`, else 0.0

    query_plan: Optional[QueryPlan] = None
    reason: Optional[str] = None
    searched_tables: list[str] = Field(default_factory=list)

    latency_ms: float = 0.0