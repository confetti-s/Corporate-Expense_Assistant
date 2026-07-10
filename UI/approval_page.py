import re
import pandas as pd
import gradio as gr

from src.db.database import SessionLocal
from src.db.models import Reimbursements, ApprovalRecords, DepartmentBudget
from src.tools.progress_tool import query_reimbursement_progress
from src.tools.approval_tool import approve_or_reject_reimbursement


def load_pending_for_approver(user_state):
    if not user_state or user_state['role'] not in ('manager', 'director', 'general_manager', 'admin'):
        return pd.DataFrame(columns=["报销单号", "申请人", "部门", "金额(元)", "费用类型", "审批级别", "审批状态"])

    db = SessionLocal()
    try:
        all_approvals = db.query(ApprovalRecords).filter_by(
            approver_id=user_state['user_id']
        ).order_by(ApprovalRecords.id.desc()).all()

        data = []
        for rec in all_approvals:
            reimb = db.query(Reimbursements).filter_by(id=rec.reimbursement_id).first()
            if not reimb:
                continue

            dept_name = reimb.department_id
            dept = db.query(DepartmentBudget).filter_by(department_id=reimb.department_id).first()
            if dept:
                dept_name = dept.department_name

            if rec.status == "pending":
                if rec.approval_level > 1:
                    prev_ok = all(
                        db.query(ApprovalRecords).filter_by(
                            reimbursement_id=reimb.id,
                            approval_level=pl
                        ).first().status == "approved"
                        for pl in range(1, rec.approval_level)
                        if db.query(ApprovalRecords).filter_by(
                            reimbursement_id=reimb.id,
                            approval_level=pl
                        ).first()
                    )
                    if not prev_ok:
                        approval_status = "等待前级审批"
                    else:
                        approval_status = "待审批"
                else:
                    approval_status = "待审批"
            elif rec.status == "approved":
                approval_status = "已通过"
            elif rec.status == "rejected":
                approval_status = "已驳回"
            else:
                approval_status = rec.status

            data.append([
                reimb.reimbursement_no,
                reimb.employee_name,
                dept_name,
                f"{reimb.total_amount:,.2f}",
                reimb.expense_type,
                f"L{rec.approval_level}",
                approval_status,
            ])

        return pd.DataFrame(data, columns=["报销单号", "申请人", "部门", "金额(元)", "费用类型", "审批级别", "审批状态"])
    finally:
        db.close()


def on_pending_select(evt: gr.SelectData):
    if not evt.value:
        return "", ""
    selected_value = str(evt.value)
    match = re.match(r'RB\d{8}', selected_value)
    if match:
        no = match.group()
        detail = query_reimbursement_progress.func(no)
        return no, detail
    return "", ""


def do_approve(selected_no, action, comment, user_state):
    if not user_state or not selected_no:
        return "请先选择一条报销单", pd.DataFrame(), ""
    action_key = "approve" if action == "通过" else "reject"
    result = approve_or_reject_reimbursement.func(selected_no, action_key, user_state['user_id'], comment or "")
    new_df = load_pending_for_approver(user_state)
    return result, new_df, ""
