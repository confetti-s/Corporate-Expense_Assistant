"""审批相关 API 路由"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from src.db.database import SessionLocal
from src.db.models import Reimbursements, ApprovalRecords, DepartmentBudget, User, DepartmentApprover
from api.auth import get_current_user
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/approval", tags=["approval"])


class ApprovalAction(BaseModel):
    reimbursement_no: str
    action: str  # "approve" or "reject"
    comment: str = ""


@router.get("/pending")
def get_pending_approvals(
    user: dict = Depends(get_current_user),
    start_date: str = None,
    end_date: str = None,
):
    if user.get("role") == "employee":
        raise HTTPException(status_code=403, detail="普通员工无权访问审批中心")

    db = SessionLocal()
    try:
        # 查询该审批人的所有待审批记录
        records = db.query(ApprovalRecords).filter_by(
            approver_id=user["user_id"],
            status="pending"
        ).all()

        items = []
        for rec in records:
            reimb = db.query(Reimbursements).filter_by(id=rec.reimbursement_id).first()
            if not reimb:
                continue
            if reimb.status not in ("pending", "reviewing"):
                continue

            # 前置级别校验
            if rec.approval_level > 1:
                prev_records = []
                for pl in range(1, rec.approval_level):
                    pr = db.query(ApprovalRecords).filter_by(
                        reimbursement_id=reimb.id,
                        approval_level=pl
                    ).first()
                    prev_records.append(pr)
                if not all(pr and pr.status == "approved" for pr in prev_records):
                    continue

            # 日期筛选
            if start_date:
                try:
                    sd = datetime.strptime(start_date, '%Y-%m-%d')
                    if reimb.created_at < sd:
                        continue
                except ValueError:
                    pass
            if end_date:
                try:
                    ed = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                    if reimb.created_at > ed:
                        continue
                except ValueError:
                    pass

            dept = db.query(DepartmentBudget).filter_by(department_id=reimb.department_id).first()

            items.append({
                "reimbursement_no": reimb.reimbursement_no,
                "applicant_name": reimb.employee_name,
                "applicant_id": reimb.employee_id,
                "department_name": dept.department_name if dept else reimb.department_id,
                "expense_type": reimb.expense_type,
                "total_amount": reimb.total_amount,
                "description": reimb.description,
                "approval_level": rec.approval_level,
                "ai_suggestion": reimb.ai_suggestion,
                "created_at": reimb.created_at.strftime('%Y-%m-%d %H:%M') if reimb.created_at else "",
            })

        items.sort(key=lambda x: x["created_at"], reverse=True)
        return {"items": items, "total": len(items)}
    finally:
        db.close()


@router.post("/action")
def do_approval(action: ApprovalAction, user: dict = Depends(get_current_user)):
    if user.get("role") == "employee":
        raise HTTPException(status_code=403, detail="普通员工无权执行审批操作")

    from src.tools.approval_tool import approve_or_reject_reimbursement

    result = approve_or_reject_reimbursement.func(
        reimbursement_no=action.reimbursement_no,
        action=action.action,
        approver_id=user["user_id"],
        comment=action.comment,
    )
    if "错误" in result or "失败" in result:
        raise HTTPException(status_code=400, detail=result)
    return {"success": True, "message": result}


@router.get("/history")
def get_approval_history(
    user: dict = Depends(get_current_user),
    page: int = 1,
    page_size: int = 20,
):
    if user.get("role") == "employee":
        raise HTTPException(status_code=403, detail="普通员工无权查看审批历史")

    db = SessionLocal()
    try:
        # 管理员和经理可以看到所有已处理的审批，普通用户只能看与自己相关的
        if user["role"] in ("manager", "admin"):
            query = db.query(ApprovalRecords).filter(ApprovalRecords.status != "pending")
        else:
            query = db.query(ApprovalRecords).filter_by(approver_id=user["user_id"])

        total = query.count()
        records = query.order_by(ApprovalRecords.approved_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        items = []
        for rec in records:
            reimb = db.query(Reimbursements).filter_by(id=rec.reimbursement_id).first()
            items.append({
                "reimbursement_no": reimb.reimbursement_no if reimb else "",
                "applicant_name": reimb.employee_name if reimb else "",
                "expense_type": reimb.expense_type if reimb else "",
                "total_amount": reimb.total_amount if reimb else 0,
                "approver_name": rec.approver_name,
                "approval_level": rec.approval_level,
                "status": rec.status,
                "comment": rec.comment,
                "approved_at": rec.approved_at.strftime('%Y-%m-%d %H:%M') if rec.approved_at else "",
            })
        return {"items": items, "total": total}
    finally:
        db.close()
