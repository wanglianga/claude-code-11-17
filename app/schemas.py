"""请求/响应 schema。"""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field


class ImportResponse(BaseModel):
    import_file_id: int
    source_ref: str
    status: str
    total_rows: int
    parsed_rows: int
    pending_rows: int
    new_results: int = 0
    new_versions: int = 0
    duplicate_rows: int = 0
    conflicts_raised: int = 0
    pending_reasons: list[dict[str, Any]] = Field(default_factory=list)
    note: str | None = None


class ConflictResolveRequest(BaseModel):
    keep_result_id: int
    note: str = Field(min_length=2, max_length=500)


class ConflictOut(BaseModel):
    id: int
    group_id: int
    result_id_a: int
    result_id_b: int
    reason: str
    status: str
    resolution_note: str | None = None
    resolved_by: str | None = None
    created_at: dt.datetime
    resolved_at: dt.datetime | None = None


class ResultOut(BaseModel):
    id: int
    group_id: int
    version: int
    source_ref: str
    record_no: str | None
    reading_text: str
    unit_original: str
    dilution_factor: float
    detection_limit_original: float | None
    conversion_chain: list[dict[str, Any]]
    dilution_applied: float
    canonical_unit: str | None
    value_type: str
    numeric_value: float | None
    lower_bound: float | None
    upper_bound: float | None
    qualitative: str
    total_mass_mg: float | None
    total_pending: bool
    calc_status: str
    calc_note: str | None
    is_superseded: bool
    created_at: dt.datetime


class GroupOut(BaseModel):
    id: int
    sample_no: str
    analyte: str
    method: str
    conflict_status: str
    current_result_id: int | None
    results: list[ResultOut] = Field(default_factory=list)


class BatchConclusionOut(BaseModel):
    id: int
    batch_no: str
    version: int
    conclusion: str
    prerequisites_met: bool
    detail: dict[str, Any]
    generated_at: dt.datetime


class ReportSubmitRequest(BaseModel):
    batch_no: str
    batch_conclusion_id: int | None = None


class ReportOut(BaseModel):
    id: int
    report_no: str
    batch_no: str
    batch_conclusion_id: int | None
    status: str
    result_refs: list[dict[str, Any]]
    payload_snapshot: dict[str, Any]
    submitted_by: str
    submitted_at: dt.datetime
    reviewed_by: str | None
    reviewed_at: dt.datetime | None
    withdraw_reason: str | None
    withdrawn_by: str | None
    withdrawn_at: dt.datetime | None
    superseded_by_id: int | None


class WithdrawRequest(BaseModel):
    reason: str = Field(min_length=2, max_length=500)
    new_report_id: int | None = None


class InvalidateRequest(BaseModel):
    sample_no: str
    reason: str = Field(min_length=2, max_length=500)


class RawRecordOut(BaseModel):
    id: int
    import_file_id: int
    source_ref: str
    record_no: str | None
    line_no: int
    sample_no: str | None
    analyte: str | None
    method: str | None
    raw_payload: dict[str, Any]
    row_hash: str
    parse_status: str
    error_reason: str | None
    created_at: dt.datetime


class PendingOut(BaseModel):
    """待处理视图：坏行 + 待补结果，采购/复核一眼看到哪些项目还不能确定。"""
    raw_pending: list[RawRecordOut]
    result_pending: list[ResultOut]
