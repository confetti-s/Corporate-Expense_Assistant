"""预算相关 API 路由"""
from fastapi import APIRouter, Depends
from src.db.database import SessionLocal
from src.db.models import DepartmentBudget, Reimbursements
from sqlalchemy import func, extract
from api.auth import get_current_user

router = APIRouter(prefix="/api/budget", tags=["budget"])

EXPENSE_TYPES = ["差旅费", "业务招待费", "日常交通费", "办公用品", "其他费用"]

# 只有行政部(D006)才有办公用品预算
OFFICE_SUPPLIES_DEPT = "D006"

MONTHS = ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月"]


def _filter_budget_query(query):
    """过滤掉非行政部的办公用品预算"""
    return query.filter(
        ~(DepartmentBudget.expense_type == "办公用品") | (DepartmentBudget.department_id == OFFICE_SUPPLIES_DEPT)
    )


@router.get("/all")
def get_all_budgets(user: dict = Depends(get_current_user)):
    role = user.get("role", "employee")
    dept_id = user.get("department_id", "")

    db = SessionLocal()
    try:
        if role == "employee":
            return {"error": "普通员工无权查看预算概览", "role": role}

        if role in ("manager", "director"):
            # 经理/总监：返回本部门各类别预算
            query = db.query(DepartmentBudget).filter_by(department_id=dept_id)
            # 非行政部过滤掉办公用品
            if dept_id != OFFICE_SUPPLIES_DEPT:
                query = query.filter(DepartmentBudget.expense_type != "办公用品")
            budgets = query.order_by(DepartmentBudget.expense_type).all()

            result = []
            for b in budgets:
                spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                    Reimbursements.department_id == dept_id,
                    Reimbursements.expense_type == b.expense_type,
                    Reimbursements.status.in_(["approved", "pending"])
                ).scalar() or 0.0
                remaining = b.budget_amount - spent
                usage_rate = round((spent / b.budget_amount * 100), 1) if b.budget_amount > 0 else 0
                result.append({
                    "expense_type": b.expense_type,
                    "department_name": b.department_name,
                    "department_id": dept_id,
                    "budget_amount": b.budget_amount,
                    "spent_amount": round(spent, 2),
                    "remaining_amount": round(remaining, 2),
                    "usage_rate": usage_rate,
                })

            return {"categories": result, "role": role, "department_id": dept_id, "department_name": budgets[0].department_name if budgets else ""}

        else:
            # 总经理/admin：返回各部门总预算（过滤非行政部的办公用品）
            departments = _filter_budget_query(
                db.query(DepartmentBudget)
            ).order_by(
                DepartmentBudget.department_id, DepartmentBudget.expense_type
            ).all()

            # 按部门汇总
            dept_map = {}
            for dept in departments:
                if dept.department_id not in dept_map:
                    dept_map[dept.department_id] = {
                        "department_id": dept.department_id,
                        "department_name": dept.department_name,
                        "budget_amount": 0.0,
                        "spent_amount": 0.0,
                    }
                spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                    Reimbursements.department_id == dept.department_id,
                    Reimbursements.expense_type == dept.expense_type,
                    Reimbursements.status.in_(["approved", "pending"])
                ).scalar() or 0.0
                dept_map[dept.department_id]["budget_amount"] += dept.budget_amount
                dept_map[dept.department_id]["spent_amount"] += spent

            result = []
            for d in dept_map.values():
                remaining = d["budget_amount"] - d["spent_amount"]
                usage_rate = round((d["spent_amount"] / d["budget_amount"] * 100), 1) if d["budget_amount"] > 0 else 0
                result.append({
                    "department_id": d["department_id"],
                    "department_name": d["department_name"],
                    "budget_amount": d["budget_amount"],
                    "spent_amount": round(d["spent_amount"], 2),
                    "remaining_amount": round(remaining, 2),
                    "usage_rate": usage_rate,
                })

            return {"departments": result, "role": role}
    finally:
        db.close()


@router.get("/summary")
def get_budget_summary(user: dict = Depends(get_current_user)):
    role = user.get("role", "employee")
    dept_id = user.get("department_id", "")

    db = SessionLocal()
    try:
        if role == "employee":
            return {"error": "普通员工无权查看预算概览", "role": role}

        if role in ("manager", "director"):
            # 经理/总监：本部门各类别汇总
            query = db.query(DepartmentBudget).filter_by(department_id=dept_id)
            if dept_id != OFFICE_SUPPLIES_DEPT:
                query = query.filter(DepartmentBudget.expense_type != "办公用品")
            budgets = query.all()
            total_budget = sum(b.budget_amount for b in budgets)
            total_spent = 0.0
            for b in budgets:
                spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                    Reimbursements.department_id == dept_id,
                    Reimbursements.expense_type == b.expense_type,
                    Reimbursements.status.in_(["approved", "pending"])
                ).scalar() or 0.0
                total_spent += spent
            return {
                "total_budget": total_budget,
                "total_spent": round(total_spent, 2),
                "total_remaining": round(total_budget - total_spent, 2),
                "usage_rate": round((total_spent / total_budget * 100), 1) if total_budget > 0 else 0,
                "role": role,
                "department_name": budgets[0].department_name if budgets else "",
                "show_departments": False,
            }

        else:
            # 总经理/admin：全公司汇总（过滤非行政部的办公用品）
            budgets = _filter_budget_query(db.query(DepartmentBudget)).all()
            total_budget = sum(b.budget_amount for b in budgets)
            total_spent = 0.0
            dept_ids = set()
            for b in budgets:
                dept_ids.add(b.department_id)
                spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                    Reimbursements.department_id == b.department_id,
                    Reimbursements.expense_type == b.expense_type,
                    Reimbursements.status.in_(["approved", "pending"])
                ).scalar() or 0.0
                total_spent += spent
            return {
                "total_budget": total_budget,
                "total_spent": round(total_spent, 2),
                "total_remaining": round(total_budget - total_spent, 2),
                "department_count": len(dept_ids),
                "usage_rate": round((total_spent / total_budget * 100), 1) if total_budget > 0 else 0,
                "role": role,
                "show_departments": True,
            }
    finally:
        db.close()


@router.get("/charts")
def get_budget_charts(user: dict = Depends(get_current_user)):
    """返回图表数据：月度报销条形图 + 类别饼图"""
    role = user.get("role", "employee")
    dept_id = user.get("department_id", "")

    db = SessionLocal()
    try:
        if role == "employee":
            return {"error": "普通员工无权查看预算概览", "role": role}

        if role in ("manager", "director"):
            # === 经理/总监：本部门数据 ===

            # 月度报销条形图：本部门每月总报销
            monthly_data = db.query(
                extract('month', Reimbursements.created_at).label('month'),
                func.sum(Reimbursements.total_amount).label('total')
            ).filter(
                Reimbursements.department_id == dept_id,
                Reimbursements.status == "approved"
            ).group_by('month').order_by('month').all()

            monthly = [0.0] * 12
            for m in monthly_data:
                idx = int(m.month) - 1
                if 0 <= idx < 12:
                    monthly[idx] = round(float(m.total), 2)

            # 类别饼图：本部门各类别报销占比（非行政部过滤办公用品）
            cat_query = db.query(
                Reimbursements.expense_type,
                func.sum(Reimbursements.total_amount).label('total')
            ).filter(
                Reimbursements.department_id == dept_id,
                Reimbursements.status == "approved"
            )
            if dept_id != OFFICE_SUPPLIES_DEPT:
                cat_query = cat_query.filter(Reimbursements.expense_type != "办公用品")
            category_data = cat_query.group_by(Reimbursements.expense_type).all()

            categories = []
            for c in category_data:
                if c.expense_type and c.total:
                    categories.append({
                        "name": c.expense_type,
                        "value": round(float(c.total), 2)
                    })

            return {
                "bar_labels": MONTHS,
                "bar_data": monthly,
                "pie_data": categories,
                "role": role,
                "bar_title": f"{db.query(DepartmentBudget).filter_by(department_id=dept_id).first().department_name if db.query(DepartmentBudget).filter_by(department_id=dept_id).first() else ''} 月度报销趋势",
                "pie_title": "各类别报销占比",
            }

        else:
            # === 总经理/admin：全公司数据 ===

            # 月度报销条形图：所有部门每月总报销
            monthly_data = db.query(
                extract('month', Reimbursements.created_at).label('month'),
                func.sum(Reimbursements.total_amount).label('total')
            ).filter(
                Reimbursements.status == "approved"
            ).group_by('month').order_by('month').all()

            monthly = [0.0] * 12
            for m in monthly_data:
                idx = int(m.month) - 1
                if 0 <= idx < 12:
                    monthly[idx] = round(float(m.total), 2)

            # 类别饼图：全公司各类别报销占比（过滤非行政部的办公用品）
            cat_query = db.query(
                Reimbursements.expense_type,
                func.sum(Reimbursements.total_amount).label('total')
            ).filter(
                Reimbursements.status == "approved"
            ).filter(
                ~(Reimbursements.expense_type == "办公用品") | (Reimbursements.department_id == OFFICE_SUPPLIES_DEPT)
            )
            category_data = cat_query.group_by(Reimbursements.expense_type).all()

            categories = []
            for c in category_data:
                if c.expense_type and c.total:
                    categories.append({
                        "name": c.expense_type,
                        "value": round(float(c.total), 2)
                    })

            return {
                "bar_labels": MONTHS,
                "bar_data": monthly,
                "pie_data": categories,
                "role": role,
                "bar_title": "全公司 月度报销趋势",
                "pie_title": "各类别报销占比",
            }
    finally:
        db.close()
