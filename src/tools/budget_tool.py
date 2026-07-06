from langchain.tools import tool
from src.db.database import SessionLocal
from src.db.models import DepartmentBudget, Reimbursements
from sqlalchemy import func

@tool("查询部门预算")
def query_department_budget(department_id: str) -> str:
    """
    查询指定部门的预算使用情况
    :param department_id: 部门ID，如 D001、D002 等
    :return: 预算信息字符串
    """
    db = SessionLocal()
    try:
        dept = db.query(DepartmentBudget).filter_by(department_id=department_id).first()
        if not dept:
            return f"未找到部门ID为 {department_id} 的预算信息"
        
        spent = db.query(func.sum(Reimbursements.total_amount)).filter(
            Reimbursements.department_id == department_id,
            Reimbursements.status == "approved"
        ).scalar() or 0.0
        
        dept.spent_amount = spent
        dept.remaining_amount = dept.budget_amount - spent
        db.commit()
        
        return f"""部门预算信息：
部门名称：{dept.department_name}
总预算：{dept.budget_amount:,.2f} 元
已使用：{dept.spent_amount:,.2f} 元
剩余预算：{dept.remaining_amount:,.2f} 元
使用率：{(dept.spent_amount / dept.budget_amount * 100):.2f}%"""
    finally:
        db.close()

@tool("检查预算是否充足")
def check_budget_sufficient(department_id: str, amount: float) -> str:
    """
    检查指定部门的预算是否足够支付报销金额
    :param department_id: 部门ID，如 D001、D002 等
    :param amount: 报销金额
    :return: 预算充足性检查结果
    """
    db = SessionLocal()
    try:
        dept = db.query(DepartmentBudget).filter_by(department_id=department_id).first()
        if not dept:
            return f"未找到部门ID为 {department_id} 的预算信息"
        
        spent = db.query(func.sum(Reimbursements.total_amount)).filter(
            Reimbursements.department_id == department_id,
            Reimbursements.status == "approved"
        ).scalar() or 0.0
        
        remaining = dept.budget_amount - spent
        
        if remaining >= amount:
            return f"预算充足！部门 {dept.department_name} 剩余预算 {remaining:,.2f} 元，报销金额 {amount:,.2f} 元在预算范围内。"
        else:
            return f"预算不足！部门 {dept.department_name} 剩余预算 {remaining:,.2f} 元，报销金额 {amount:,.2f} 元超出预算 {amount - remaining:,.2f} 元，需要特殊审批。"
    finally:
        db.close()

@tool("获取所有部门预算")
def get_all_department_budgets() -> str:
    """
    获取所有部门的预算使用情况
    :return: 所有部门预算信息字符串
    """
    db = SessionLocal()
    try:
        departments = db.query(DepartmentBudget).all()
        result = "所有部门预算信息：\n\n"
        
        for dept in departments:
            spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                Reimbursements.department_id == dept.department_id,
                Reimbursements.status == "approved"
            ).scalar() or 0.0
            
            remaining = dept.budget_amount - spent
            usage_rate = (spent / dept.budget_amount * 100) if dept.budget_amount > 0 else 0
            
            result += f"""部门名称：{dept.department_name} (ID: {dept.department_id})
总预算：{dept.budget_amount:,.2f} 元
已使用：{spent:,.2f} 元
剩余预算：{remaining:,.2f} 元
使用率：{usage_rate:.2f}%
------------------------
"""
        
        return result
    finally:
        db.close()