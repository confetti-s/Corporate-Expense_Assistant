"""预算相关 API 路由"""
from fastapi import APIRouter, Depends
from src.db.database import SessionLocal
from src.db.models import DepartmentBudget, Reimbursements
from sqlalchemy import func
from api.auth import get_current_user

router = APIRouter(prefix="/api/budget", tags=["budget"])

EXPENSE_TYPES = ["差旅费", "业务招待费", "日常交通费", "办公用品", "其他费用"]


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
            budgets = db.query(DepartmentBudget).filter_by(
                department_id=dept_id
            ).order_by(DepartmentBudget.expense_type).all()

            result = []
            for b in budgets:
                spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                    Reimbursements.department_id == dept_id,
                    Reimbursements.expense_type == b.expense_type,
                    Reimbursements.status == "approved"
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
            # 总经理/admin：返回各部门总预算
            departments = db.query(DepartmentBudget).order_by(
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
                    Reimbursements.status == "approved"
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
            budgets = db.query(DepartmentBudget).filter_by(department_id=dept_id).all()
            total_budget = sum(b.budget_amount for b in budgets)
            total_spent = 0.0
            for b in budgets:
                spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                    Reimbursements.department_id == dept_id,
                    Reimbursements.expense_type == b.expense_type,
                    Reimbursements.status == "approved"
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
            # 总经理/admin：全公司汇总
            budgets = db.query(DepartmentBudget).all()
            total_budget = sum(b.budget_amount for b in budgets)
            total_spent = 0.0
            dept_ids = set()
            for b in budgets:
                dept_ids.add(b.department_id)
                spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                    Reimbursements.department_id == b.department_id,
                    Reimbursements.expense_type == b.expense_type,
                    Reimbursements.status == "approved"
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
