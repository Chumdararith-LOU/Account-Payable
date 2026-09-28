"""Request/response schemas for the APMatch API.

Pydantic v2 models mirroring the deterministic pipeline's outputs. All
enum-valued fields serialize as their ``.value`` string. Error responses are
always enum-coded (``error_code``) plus a stable detail string — never
free text, never user data, never a stack trace.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


class FailureOut(BaseModel):
    code: str  # CheckCode.value or MatchCode.value
    severity: str  # Severity.value
    location: str
    expected: str
    actual: str
    delta: str


class MatchResponse(BaseModel):
    run_id: str
    route: str  # Route.value
    route_reason: str  # RouteReason.value
    score: float  # ConfidenceScore.value
    remark: str
    invoice_number: str | None
    po_number: str | None
    grn_number: str | None
    pard_ref: str | None
    validation_failures: list[FailureOut]
    match_failures: list[FailureOut]


class AuditResponse(BaseModel):
    run_id: str
    run_timestamp: datetime
    route: str
    route_reason: str
    score: float
    remark: str
    invoice_number: str
    po_number: str | None
    grn_number: str | None
    pard_ref: str | None
    validation_failures: list[FailureOut]
    match_failures: list[FailureOut]
    input_hash: str


class RouteCountsOut(BaseModel):
    auto_approve: int
    human_review: int
    reject: int
    total: int


class RecentRunOut(BaseModel):
    run_id: str
    run_timestamp: datetime
    invoice_number: str
    route: str
    route_reason: str
    score: float
    remark: str


class ErrorResponse(BaseModel):
    error_code: str  # e.g. "AUTH_MISSING", "MISSING_DOCUMENT"
    detail: str  # human-readable, but never contains user data
