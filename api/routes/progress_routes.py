"""进度查询相关 API 路由"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from src.db.database import SessionLocal
from src.db.models import Reimbursements, ApprovalRecords, Invoice, DepartmentBudget
from api.auth import get_current_user
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/progress", tags=["progress"])


STATUS_MAP = {
    "draft": "草稿",
    "pending": "待审批",
    "reviewing": "审批中",
    "approved": "已通过",
    "rejected": "已驳回",
    "split": "已拆分",
}


@router.get("/list")
def list_reimbursements(
    user: dict = Depends(get_current_user),
    status: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
):
    db = SessionLocal()
    try:
        query = db.query(Reimbursements)
        if user["role"] not in ("manager", "admin"):
            query = query.filter_by(employee_id=user["user_id"])

        if status and status != "all":
            query = query.filter_by(status=status)
        if start_date:
            try:
                sd = datetime.strptime(start_date, '%Y-%m-%d')
                query = query.filter(Reimbursements.created_at >= sd)
            except ValueError:
                pass
        if end_date:
            try:
                ed = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                query = query.filter(Reimbursements.created_at <= ed)
            except ValueError:
                pass

        total = query.count()
        reimbursements = query.order_by(Reimbursements.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        items = []
        for r in reimbursements:
            dept = db.query(DepartmentBudget).filter_by(department_id=r.department_id).first()
            items.append({
                "id": r.id,
                "reimbursement_no": r.reimbursement_no,
                "employee_name": r.employee_name,
                "employee_id": r.employee_id,
                "department_name": dept.department_name if dept else r.department_id,
                "expense_type": r.expense_type,
                "total_amount": r.total_amount,
                "description": r.description,
                "status": r.status,
                "status_label": STATUS_MAP.get(r.status, r.status),
                "created_at": r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else "",
            })
        return {"items": items, "total": total, "page": page, "page_size": page_size}
    finally:
        db.close()


@router.get("/detail/{reimbursement_no}")
def get_reimbursement_detail(reimbursement_no: str, user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        r = db.query(Reimbursements).filter_by(reimbursement_no=reimbursement_no).first()
        if not r:
            return {"error": "未找到该报销单"}

        invoices = db.query(Invoice).filter_by(reimbursement_id=r.id).all()
        approval_records = db.query(ApprovalRecords).filter_by(
            reimbursement_id=r.id
        ).order_by(ApprovalRecords.approval_level).all()

        dept = db.query(DepartmentBudget).filter_by(department_id=r.department_id).first()

        return {
            "reimbursement_no": r.reimbursement_no,
            "source_reimbursement_no": r.source_reimbursement_no,
            "employee_name": r.employee_name,
            "employee_id": r.employee_id,
            "department_name": dept.department_name if dept else r.department_id,
            "expense_type": r.expense_type,
            "total_amount": r.total_amount,
            "description": r.description,
            "status": r.status,
            "status_label": STATUS_MAP.get(r.status, r.status),
            "ai_suggestion": r.ai_suggestion,
            "confirmed": r.confirmed,
            "created_at": r.created_at.strftime('%Y-%m-%d %H:%M') if r.created_at else "",
            "updated_at": r.updated_at.strftime('%Y-%m-%d %H:%M') if r.updated_at else "",
            "invoices": [{
                "id": inv.id,
                "invoice_type_name": inv.invoice_type_name,
                "amount": inv.amount,
                "invoice_date": inv.invoice_date,
                "is_valid": inv.is_valid,
                "invalid_reason": inv.invalid_reason,
                "file_path": inv.file_path,
            } for inv in invoices],
            "approval_records": [{
                "approver_name": rec.approver_name,
                "approver_id": rec.approver_id,
                "approval_level": rec.approval_level,
                "status": rec.status,
                "comment": rec.comment,
                "approved_at": rec.approved_at.strftime('%Y-%m-%d %H:%M') if rec.approved_at else None,
            } for rec in approval_records],
        }
    finally:
        db.close()


@router.get("/stats")
def get_progress_stats(user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        base_query = db.query(Reimbursements)
        if user["role"] not in ("manager", "admin"):
            base_query = base_query.filter_by(employee_id=user["user_id"])

        pending = base_query.filter(Reimbursements.status.in_(["pending", "reviewing"])).count()
        approved = base_query.filter_by(status="approved").count()
        rejected = base_query.filter_by(status="rejected").count()

        this_month = datetime.now().replace(day=1)
        month_amount = db.query(func.sum(Reimbursements.total_amount)).filter(
            Reimbursements.employee_id == user["user_id"] if user["role"] not in ("manager", "admin") else True,
            Reimbursements.created_at >= this_month
        ).scalar() or 0.0

        return {
            "pending_count": pending,
            "approved_count": approved,
            "rejected_count": rejected,
            "month_total_amount": round(float(month_amount), 2),
        }
    finally:
        db.close()
