from langchain.tools import tool
from src.db.database import SessionLocal
from src.db.models import DepartmentBudget, Reimbursements
from sqlalchemy import func
from datetime import datetime

# 五大费用类型
EXPENSE_TYPES = ["差旅费", "业务招待费", "日常交通费", "办公用品", "其他费用"]


@tool("查询部门预算")
def query_department_budget(department_id: str, expense_type: str = "") -> str:
    """
    查询指定部门的预算使用情况，支持按费用类别筛选
    :param department_id: 部门ID，如 D001、D002 等
    :param expense_type: 费用类型（可选），如 差旅费、业务招待费、日常交通费、办公用品、其他费用
    :return: 预算信息字符串
    """
    db = SessionLocal()
    try:
        if expense_type:
            budgets = db.query(DepartmentBudget).filter_by(
                department_id=department_id, expense_type=expense_type
            ).all()
        else:
            budgets = db.query(DepartmentBudget).filter_by(
                department_id=department_id
            ).order_by(DepartmentBudget.expense_type).all()

        if not budgets:
            return f"未找到部门ID为 {department_id} 的预算信息"

        # 汇总信息
        dept_name = budgets[0].department_name
        total_budget = sum(b.budget_amount for b in budgets)
        total_spent = 0.0

        result = f"部门预算信息：{dept_name}（{department_id}）\n\n"
        for b in budgets:
            # 实时计算已支出
            spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                Reimbursements.department_id == department_id,
                Reimbursements.expense_type == b.expense_type,
                Reimbursements.status == "approved"
            ).scalar() or 0.0
            b.spent_amount = spent
            b.remaining_amount = b.budget_amount - spent
            total_spent += spent

            usage_rate = (spent / b.budget_amount * 100) if b.budget_amount > 0 else 0
            result += f"【{b.expense_type}】预算 {b.budget_amount:,.2f} 元 | 已用 {spent:,.2f} 元 | 剩余 {b.remaining_amount:,.2f} 元 | 使用率 {usage_rate:.1f}%\n"

        db.commit()
        total_remaining = total_budget - total_spent
        result += f"\n--- 汇总 ---\n总预算：{total_budget:,.2f} 元 | 总已用：{total_spent:,.2f} 元 | 总剩余：{total_remaining:,.2f} 元"
        return result
    finally:
        db.close()


@tool("检查预算是否充足")
def check_budget_sufficient(department_id: str, amount: float, expense_type: str = "") -> str:
    """
    检查指定部门的预算是否足够支付报销金额
    :param department_id: 部门ID，如 D001、D002 等
    :param amount: 报销金额
    :param expense_type: 费用类型（必填），如 差旅费、业务招待费、日常交通费、办公用品、其他费用
    :return: 预算充足性检查结果
    """
    db = SessionLocal()
    try:
        if expense_type:
            budget = db.query(DepartmentBudget).filter_by(
                department_id=department_id, expense_type=expense_type
            ).first()
            if not budget:
                return f"未找到部门 {department_id} 的 {expense_type} 预算信息"

            spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                Reimbursements.department_id == department_id,
                Reimbursements.expense_type == expense_type,
                Reimbursements.status == "approved"
            ).scalar() or 0.0

            remaining = budget.budget_amount - spent
            if remaining >= amount:
                return f"预算充足！{budget.department_name}【{expense_type}】剩余预算 {remaining:,.2f} 元，报销金额 {amount:,.2f} 元在预算范围内。"
            else:
                return f"预算不足！{budget.department_name}【{expense_type}】剩余预算 {remaining:,.2f} 元，报销金额 {amount:,.2f} 元超出预算 {amount - remaining:,.2f} 元，需要特殊审批。"
        else:
            # 无类别时查总预算
            budgets = db.query(DepartmentBudget).filter_by(department_id=department_id).all()
            if not budgets:
                return f"未找到部门ID为 {department_id} 的预算信息"
            total_budget = sum(b.budget_amount for b in budgets)
            total_spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                Reimbursements.department_id == department_id,
                Reimbursements.status == "approved"
            ).scalar() or 0.0
            remaining = total_budget - total_spent
            if remaining >= amount:
                return f"预算充足！剩余总预算 {remaining:,.2f} 元，报销金额 {amount:,.2f} 元在预算范围内。"
            else:
                return f"预算不足！剩余总预算 {remaining:,.2f} 元，报销金额 {amount:,.2f} 元超出预算 {amount - remaining:,.2f} 元，需要特殊审批。"
    finally:
        db.close()


@tool("获取所有部门预算")
def get_all_department_budgets() -> str:
    """
    获取所有部门的预算使用情况（按部门+类别展示）
    :return: 所有部门预算信息字符串
    """
    db = SessionLocal()
    try:
        departments = db.query(DepartmentBudget).order_by(
            DepartmentBudget.department_id, DepartmentBudget.expense_type
        ).all()

        # 按部门分组
        dept_map = {}
        for dept in departments:
            if dept.department_id not in dept_map:
                dept_map[dept.department_id] = {"name": dept.department_name, "items": []}

            spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                Reimbursements.department_id == dept.department_id,
                Reimbursements.expense_type == dept.expense_type,
                Reimbursements.status == "approved"
            ).scalar() or 0.0

            remaining = dept.budget_amount - spent
            usage_rate = (spent / dept.budget_amount * 100) if dept.budget_amount > 0 else 0
            dept.spent_amount = spent
            dept.remaining_amount = remaining

            dept_map[dept.department_id]["items"].append(
                f"  {dept.expense_type}：预算 {dept.budget_amount:,.2f} | 已用 {spent:,.2f} | 剩余 {remaining:,.2f} | {usage_rate:.1f}%"
            )

        db.commit()

        result = "所有部门预算信息：\n\n"
        for dept_id, info in dept_map.items():
            total_budget = 0
            total_spent = 0
            for item in info["items"]:
                result += item + "\n"
                # 从 items 解析数据太复杂，直接汇总
            for dept in departments:
                if dept.department_id == dept_id:
                    total_budget += dept.budget_amount
                    total_spent += dept.spent_amount
            result += f"  --- 汇总：总预算 {total_budget:,.2f} | 总已用 {total_spent:,.2f} ---\n\n"

        return result
    finally:
        db.close()


def update_budget_spent():
    """
    根据已审批通过的报销单金额，按部门+费用类别更新预算使用情况
    """
    db = SessionLocal()
    try:
        for dept_budget in db.query(DepartmentBudget).all():
            spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                Reimbursements.department_id == dept_budget.department_id,
                Reimbursements.expense_type == dept_budget.expense_type,
                Reimbursements.status == "approved"
            ).scalar() or 0.0
            dept_budget.spent_amount = spent
            dept_budget.remaining_amount = dept_budget.budget_amount - spent
            dept_budget.updated_at = datetime.now()
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[预算更新失败] {e}")
    finally:
        db.close()
