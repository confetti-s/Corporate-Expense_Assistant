from langchain.tools import tool
from src.db.database import SessionLocal
from src.db.models import Reimbursements, ApprovalRecords
from datetime import datetime, timedelta

@tool("查询报销进度")
def query_reimbursement_progress(reimbursement_no: str) -> str:
    """
    根据报销单号查询报销审批进度
    :param reimbursement_no: 报销单号，如 RB20260001
    :return: 报销进度信息字符串
    """
    db = SessionLocal()
    try:
        reimbursement = db.query(Reimbursements).filter_by(reimbursement_no=reimbursement_no).first()
        if not reimbursement:
            return f"未找到报销单号为 {reimbursement_no} 的记录"
        
        records = db.query(ApprovalRecords).filter_by(reimbursement_id=reimbursement.id).order_by(ApprovalRecords.approval_level).all()
        
        status_map = {
            "pending": "待审批",
            "reviewing": "审批中",
            "approved": "已通过",
            "rejected": "已驳回"
        }
        
        result = f"""报销单信息：
报销单号：{reimbursement.reimbursement_no}
员工姓名：{reimbursement.employee_name}
部门：{reimbursement.department_id}
费用类型：{reimbursement.expense_type}
总金额：{reimbursement.total_amount:,.2f} 元
当前状态：{status_map.get(reimbursement.status, reimbursement.status)}
是否需要特殊审批：{'是' if reimbursement.need_special_approval else '否'}
提交时间：{reimbursement.created_at.strftime('%Y-%m-%d %H:%M')}

审批流程：
"""
        
        if not records:
            result += "暂无审批记录"
        else:
            for record in records:
                approved_time = record.approved_at.strftime('%Y-%m-%d %H:%M') if record.approved_at else "待处理"
                result += f"""第{record.approval_level}级审批：
  审批人：{record.approver_name}
  状态：{status_map.get(record.status, record.status)}
  备注：{record.comment}
  审批时间：{approved_time}
"""
        
        return result
    finally:
        db.close()

@tool("按日期范围查询报销")
def query_reimbursements_by_date(start_date: str, end_date: str, employee_id: str = None) -> str:
    """
    根据日期范围查询报销记录
    :param start_date: 开始日期，格式 YYYY-MM-DD
    :param end_date: 结束日期，格式 YYYY-MM-DD
    :param employee_id: 员工ID（可选）
    :return: 报销记录列表字符串
    """
    db = SessionLocal()
    try:
        query = db.query(Reimbursements).filter(
            Reimbursements.created_at >= datetime.strptime(start_date, '%Y-%m-%d'),
            Reimbursements.created_at <= datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        )
        
        if employee_id:
            query = query.filter_by(employee_id=employee_id)
        
        reimbursements = query.all()
        
        if not reimbursements:
            return f"在 {start_date} 至 {end_date} 期间未找到报销记录"
        
        status_map = {
            "pending": "待审批",
            "reviewing": "审批中",
            "approved": "已通过",
            "rejected": "已驳回"
        }
        
        result = f"报销记录查询结果（共 {len(reimbursements)} 条）：\n\n"
        
        for r in reimbursements:
            result += f"""报销单号：{r.reimbursement_no}
员工姓名：{r.employee_name}
部门：{r.department_id}
费用类型：{r.expense_type}
金额：{r.total_amount:,.2f} 元
状态：{status_map.get(r.status, r.status)}
提交时间：{r.created_at.strftime('%Y-%m-%d %H:%M')}
------------------------
"""
        
        return result
    finally:
        db.close()