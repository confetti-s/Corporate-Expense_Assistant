"""预算相关 API 路由"""
from fastapi import APIRouter, Depends
from src.db.database import SessionLocal
from src.db.models import DepartmentBudget, Reimbursements
from sqlalchemy import func
from api.auth import get_current_user

router = APIRouter(prefix="/api/budget", tags=["budget"])


@router.get("/all")
def get_all_budgets(user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        departments = db.query(DepartmentBudget).all()
        result = []
        for dept in departments:
            spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                Reimbursements.department_id == dept.department_id,
                Reimbursements.status == "approved"
            ).scalar() or 0.0
            remaining = dept.budget_amount - spent
            usage_rate = round((spent / dept.budget_amount * 100), 1) if dept.budget_amount > 0 else 0
            result.append({
                "department_id": dept.department_id,
                "department_name": dept.department_name,
                "budget_amount": dept.budget_amount,
                "spent_amount": round(spent, 2),
                "remaining_amount": round(remaining, 2),
                "usage_rate": usage_rate,
            })
        return {"departments": result}
    finally:
        db.close()


@router.get("/summary")
def get_budget_summary(user: dict = Depends(get_current_user)):
    db = SessionLocal()
    try:
        departments = db.query(DepartmentBudget).all()
        total_budget = sum(d.budget_amount for d in departments)
        total_spent = 0.0
        dept_count = len(departments)
        for dept in departments:
            spent = db.query(func.sum(Reimbursements.total_amount)).filter(
                Reimbursements.department_id == dept.department_id,
                Reimbursements.status == "approved"
            ).scalar() or 0.0
            total_spent += spent
        return {
            "total_budget": total_budget,
            "total_spent": round(total_spent, 2),
            "total_remaining": round(total_budget - total_spent, 2),
            "department_count": dept_count,
            "usage_rate": round((total_spent / total_budget * 100), 1) if total_budget > 0 else 0,
        }
    finally:
        db.close()
