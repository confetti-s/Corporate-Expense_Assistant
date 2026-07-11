import re
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

from src.db.database import SessionLocal
from src.db.models import DepartmentBudget, Reimbursements, User
from sqlalchemy import func


def _get_user_role_and_dept(employee_id):
    """根据employee_id获取用户角色和部门ID"""
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(user_id=employee_id).first()
        if not user:
            return "employee", ""
        return user.role, user.department_id or ""
    finally:
        db.close()


def get_budget_chart_for_user(employee_id):
    """根据用户角色生成对应的预算图表"""
    role, dept_id = _get_user_role_and_dept(employee_id)

    if role == "employee":
        return None

    db = SessionLocal()
    try:
        if role in ("manager", "director"):
            # 经理/总监：本部门各类别预算
            budgets = db.query(DepartmentBudget).filter_by(
                department_id=dept_id
            ).order_by(DepartmentBudget.expense_type).all()

            if not budgets:
                return None

            dept_name = budgets[0].department_name
            categories = []
            budget_amounts = []
            spent_amounts = []
            remaining_amounts = []

            for b in budgets:
                spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                    Reimbursements.department_id == dept_id,
                    Reimbursements.expense_type == b.expense_type,
                    Reimbursements.status == "approved"
                ).scalar() or 0.0
                remaining = b.budget_amount - spent

                categories.append(b.expense_type)
                budget_amounts.append(b.budget_amount)
                spent_amounts.append(spent)
                remaining_amounts.append(remaining)

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

            x = range(len(categories))
            ax1.bar(x, budget_amounts, label='总预算', color='#4CAF50', alpha=0.7)
            ax1.bar(x, spent_amounts, label='已使用', color='#FF9800')
            ax1.set_xticks(x)
            ax1.set_xticklabels(categories, fontsize=9)
            ax1.set_ylabel('金额（元）')
            ax1.set_title(f'{dept_name} 各类别预算使用情况')
            ax1.legend()
            ax1.ticklabel_format(axis='y', style='plain')

            colors = ['#4CAF50', '#8BC34A', '#CDDC39', '#FFC107', '#FF5722']
            ax2.pie(remaining_amounts, labels=categories, autopct='%1.1f%%',
                    colors=colors[:len(categories)])
            ax2.set_title(f'{dept_name} 剩余预算占比')

        else:
            # 总经理/admin：各部门总预算
            departments = db.query(DepartmentBudget).order_by(
                DepartmentBudget.department_id
            ).all()

            dept_map = {}
            for dept in departments:
                if dept.department_id not in dept_map:
                    dept_map[dept.department_id] = {
                        "name": dept.department_name,
                        "budget": 0.0,
                        "spent": 0.0,
                    }
                spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                    Reimbursements.department_id == dept.department_id,
                    Reimbursements.expense_type == dept.expense_type,
                    Reimbursements.status == "approved"
                ).scalar() or 0.0
                dept_map[dept.department_id]["budget"] += dept.budget_amount
                dept_map[dept.department_id]["spent"] += spent

            dept_names = [v["name"] for v in dept_map.values()]
            budget_amounts = [v["budget"] for v in dept_map.values()]
            spent_amounts = [v["spent"] for v in dept_map.values()]
            remaining_amounts = [v["budget"] - v["spent"] for v in dept_map.values()]

            if not dept_names:
                return None

            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

            x = range(len(dept_names))
            ax1.bar(x, budget_amounts, label='总预算', color='#4CAF50', alpha=0.7)
            ax1.bar(x, spent_amounts, label='已使用', color='#FF9800')
            ax1.set_xticks(x)
            ax1.set_xticklabels(dept_names, fontsize=9)
            ax1.set_ylabel('金额（元）')
            ax1.set_title('各部门预算使用情况')
            ax1.legend()
            ax1.ticklabel_format(axis='y', style='plain')

            colors = ['#4CAF50', '#8BC34A', '#CDDC39', '#FFC107', '#FF5722', '#9C27B0']
            ax2.pie(remaining_amounts, labels=dept_names, autopct='%1.1f%%',
                    colors=colors[:len(dept_names)])
            ax2.set_title('各部门剩余预算占比')

        plt.tight_layout()
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        plt.savefig(tmp.name, format='png', dpi=100)
        plt.close()
        return tmp.name
    except Exception as e:
        print(f"预算图表生成错误: {e}")
        return None
    finally:
        db.close()


def get_budget_text_for_user(employee_id):
    """根据用户角色生成预算文字描述"""
    role, dept_id = _get_user_role_and_dept(employee_id)

    if role == "employee":
        return "普通员工无权查看预算概览，如需了解请咨询部门经理。"

    db = SessionLocal()
    try:
        if role in ("manager", "director"):
            budgets = db.query(DepartmentBudget).filter_by(
                department_id=dept_id
            ).order_by(DepartmentBudget.expense_type).all()

            if not budgets:
                return f"未找到部门 {dept_id} 的预算信息"

            dept_name = budgets[0].department_name
            total_budget = sum(b.budget_amount for b in budgets)
            total_spent = 0.0

            result = f"部门预算信息：{dept_name}（{dept_id}）\n\n"
            for b in budgets:
                spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                    Reimbursements.department_id == dept_id,
                    Reimbursements.expense_type == b.expense_type,
                    Reimbursements.status == "approved"
                ).scalar() or 0.0
                remaining = b.budget_amount - spent
                total_spent += spent
                usage_rate = (spent / b.budget_amount * 100) if b.budget_amount > 0 else 0
                result += f"【{b.expense_type}】预算 {b.budget_amount:,.2f} 元 | 已用 {spent:,.2f} 元 | 剩余 {remaining:,.2f} 元 | 使用率 {usage_rate:.1f}%\n"

            total_remaining = total_budget - total_spent
            result += f"\n--- 汇总 ---\n总预算：{total_budget:,.2f} 元 | 总已用：{total_spent:,.2f} 元 | 总剩余：{total_remaining:,.2f} 元"
            return result

        else:
            departments = db.query(DepartmentBudget).order_by(
                DepartmentBudget.department_id
            ).all()

            dept_map = {}
            for dept in departments:
                if dept.department_id not in dept_map:
                    dept_map[dept.department_id] = {"name": dept.department_name, "budget": 0.0, "spent": 0.0}
                spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                    Reimbursements.department_id == dept.department_id,
                    Reimbursements.expense_type == dept.expense_type,
                    Reimbursements.status == "approved"
                ).scalar() or 0.0
                dept_map[dept.department_id]["budget"] += dept.budget_amount
                dept_map[dept.department_id]["spent"] += spent

            total_budget = sum(v["budget"] for v in dept_map.values())
            total_spent = sum(v["spent"] for v in dept_map.values())

            result = "公司各部门预算概览：\n\n"
            for dept_id_key, info in dept_map.items():
                remaining = info["budget"] - info["spent"]
                usage_rate = (info["spent"] / info["budget"] * 100) if info["budget"] > 0 else 0
                result += f"【{info['name']}】预算 {info['budget']:,.2f} 元 | 已用 {info['spent']:,.2f} 元 | 剩余 {remaining:,.2f} 元 | 使用率 {usage_rate:.1f}%\n"

            total_remaining = total_budget - total_spent
            result += f"\n--- 汇总 ---\n公司总预算：{total_budget:,.2f} 元 | 总已用：{total_spent:,.2f} 元 | 总剩余：{total_remaining:,.2f} 元"
            return result
    finally:
        db.close()


def update_budget(employee_id="E001"):
    """Gradio端更新预算显示"""
    chart = get_budget_chart_for_user(employee_id)
    text = get_budget_text_for_user(employee_id)
    return chart, text
