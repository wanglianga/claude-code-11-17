"""报告批准流。

- submit：固化当前结果版本引用（result_refs），报告进入 submitted。
- approve：批准请求重新读取结果版本；若引用的结果已被修订/失效/冲突重开，
  版本漂移 -> 拒绝批准并打回，不基于旧快照签发。
- withdraw：已签发报告只能撤回，不能改原文；撤回后用新报告接续（superseded_by 链），
  历史全部保留。
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import (
    CONFLICT_OPEN,
    REPORT_APPROVED,
    REPORT_SUBMITTED,
    REPORT_WITHDRAWN,
    AuditEvent,
    BatchConclusion,
    Report,
    ResultGroup,
    Sample,
    StandardizedResult,
    utcnow,
)


class ReportError(RuntimeError):
    pass


def _current_refs(db: Session, batch_no: str) -> list[dict]:
    sample_nos = [s.sample_no for s in db.query(Sample).filter_by(batch_no=batch_no).all()]
    groups = (
        db.query(ResultGroup)
        .filter(ResultGroup.sample_no.in_(sample_nos or ["__none__"]))
        .all()
    )
    refs = []
    for g in groups:
        if g.current_result_id is None:
            refs.append(
                {
                    "sample_no": g.sample_no,
                    "analyte": g.analyte,
                    "method": g.method,
                    "result_id": None,
                    "version": None,
                    "is_superseded": None,
                    "conflict_status": g.conflict_status,
                }
            )
            continue
        r = db.get(StandardizedResult, g.current_result_id)
        refs.append(
            {
                "sample_no": g.sample_no,
                "analyte": g.analyte,
                "method": g.method,
                "result_id": r.id,
                "version": r.version,
                "is_superseded": r.is_superseded,
                "conflict_status": g.conflict_status,
            }
        )
    return refs


def submit_report(
    db: Session, batch_no: str, inspector: str, conclusion_id: int | None = None
) -> Report:
    conclusion = (
        db.get(BatchConclusion, conclusion_id)
        if conclusion_id
        else (
            db.query(BatchConclusion)
            .filter_by(batch_no=batch_no)
            .order_by(BatchConclusion.version.desc())
            .first()
        )
    )
    if conclusion is None:
        raise ReportError(f"批次 {batch_no} 尚无批次结论，无法提交报告")
    refs = _current_refs(db, batch_no)
    report = Report(
        report_no=f"RPT-{batch_no}-{uuid.uuid4().hex[:8]}",
        batch_no=batch_no,
        batch_conclusion_id=conclusion.id,
        status=REPORT_SUBMITTED,
        result_refs=refs,
        payload_snapshot={
            "conclusion": conclusion.conclusion,
            "conclusion_version": conclusion.version,
            "detail": conclusion.detail,
        },
        submitted_by=inspector,
    )
    db.add(report)
    db.add(AuditEvent(event_type="report_submitted", actor=inspector,
                      target=report.report_no, detail={"refs": refs}))
    db.flush()
    return report


def _detect_drift(db: Session, report: Report) -> list[str]:
    """批准前重读：比对提交时的版本引用与当前生效版本。"""
    drifts: list[str] = []
    for ref in report.result_refs:
        group = (
            db.query(ResultGroup)
            .filter_by(sample_no=ref["sample_no"], analyte=ref["analyte"], method=ref["method"])
            .first()
        )
        if group is None:
            drifts.append(f"{ref['sample_no']}/{ref['analyte']} 的结果组已不存在")
            continue
        if group.conflict_status == CONFLICT_OPEN:
            drifts.append(f"{ref['sample_no']}/{ref['analyte']} 出现未处理冲突，原批准依据失效")
        if group.current_result_id != ref["result_id"]:
            drifts.append(
                f"{ref['sample_no']}/{ref['analyte']} 生效版本已由 result_id={ref['result_id']} "
                f"变更为 {group.current_result_id}，需重新提交"
            )
            continue
        current = db.get(StandardizedResult, ref["result_id"])
        if current is None or current.is_superseded:
            drifts.append(f"{ref['sample_no']}/{ref['analyte']} 引用结果已被修订失效")
    return drifts


def approve_report(db: Session, report_id: int, reviewer: str) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise ReportError(f"报告 {report_id} 不存在")
    if report.status == REPORT_WITHDRAWN:
        raise ReportError("报告已撤回，不能批准；请基于新修订重新提交报告")
    if report.status == REPORT_APPROVED:
        raise ReportError("报告已批准，请勿重复操作")

    drifts = _detect_drift(db, report)
    if drifts:
        db.add(AuditEvent(event_type="report_approval_rejected", actor=reviewer,
                          target=report.report_no, detail={"drifts": drifts}))
        db.flush()
        raise ReportError("批准前重读发现结果版本漂移：" + "；".join(drifts))

    report.status = REPORT_APPROVED
    report.reviewed_by = reviewer
    report.reviewed_at = utcnow()
    db.add(AuditEvent(event_type="report_approved", actor=reviewer,
                      target=report.report_no, detail={"report_id": report.id}))
    db.flush()
    return report


def withdraw_report(
    db: Session, report_id: int, reviewer: str, reason: str, new_report_id: int | None = None
) -> Report:
    report = db.get(Report, report_id)
    if report is None:
        raise ReportError(f"报告 {report_id} 不存在")
    if report.status != REPORT_APPROVED:
        raise ReportError("只有已签发（approved）的报告允许撤回")
    report.status = REPORT_WITHDRAWN
    report.withdraw_reason = reason
    report.withdrawn_by = reviewer
    report.withdrawn_at = utcnow()
    if new_report_id is not None:
        new_report = db.get(Report, new_report_id)
        if new_report is None:
            raise ReportError(f"接续报告 {new_report_id} 不存在")
        report.superseded_by_id = new_report_id
    db.add(AuditEvent(
        event_type="report_withdrawn", actor=reviewer, target=report.report_no,
        detail={"reason": reason, "superseded_by": new_report_id},
    ))
    db.flush()
    return report
