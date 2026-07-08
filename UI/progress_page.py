import re
import pandas as pd
import gradio as gr

from src.db.database import SessionLocal
from src.db.models import Reimbursements
from src.tools.progress_tool import query_reimbursement_progress, query_reimbursements_by_date
from UI.constants import STATUS_MAP


def load_my_reimbursements(user_state):
    if not user_state:
        return pd.DataFrame(columns=["报销单号", "费用类型", "金额(元)", "状态", "创建日期"])

    db = SessionLocal()
    try:
        records = db.query(Reimbursements).filter_by(
            employee_id=user_state['user_id']
        ).order_by(Reimbursements.created_at.desc()).all()

        data = []
        for r in records:
            data.append([
                r.reimbursement_no,
                r.expense_type,
                f"{r.total_amount:,.2f}",
                STATUS_MAP.get(r.status, r.status),
                r.created_at.strftime('%Y-%m-%d'),
            ])

        return pd.DataFrame(data, columns=["报销单号", "费用类型", "金额(元)", "状态", "创建日期"])
    finally:
        db.close()


def on_reimb_select(evt: gr.SelectData, user_state):
    if not evt.value:
        return ""
    try:
        selected_value = str(evt.value)
        match = re.match(r'RB\d{8}', selected_value)
        if match:
            return query_reimbursement_progress.func(match.group())
    except Exception:
        pass
    return ""


def query_progress_ui(reimbursement_no):
    if not reimbursement_no:
        return "请输入报销单号"
    return query_reimbursement_progress.func(reimbursement_no)


def query_by_date_range(start_date, end_date, user_state):
    if not start_date or not end_date:
        return "请输入开始和结束日期（格式：YYYY-MM-DD）"
    emp_id = user_state['user_id'] if user_state else None
    return query_reimbursements_by_date.func(start_date, end_date, emp_id)
