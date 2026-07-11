from sqlalchemy.orm import Session
from sqlalchemy import func
from src.db.models import Reimbursements, DepartmentBudget, ApprovalRecords, User, DepartmentApprover, Invoice
from src.db.auth import hash_password
from datetime import datetime, timedelta
import random
import json


def seed_department_budget(db: Session):
    departments = [
        {"department_id": "D001", "department_name": "技术部", "budget_amount": 500000.0},
        {"department_id": "D002", "department_name": "市场部", "budget_amount": 300000.0},
        {"department_id": "D003", "department_name": "财务部", "budget_amount": 100000.0},
        {"department_id": "D004", "department_name": "人力资源部", "budget_amount": 80000.0},
        {"department_id": "D005", "department_name": "销售部", "budget_amount": 800000.0},
        {"department_id": "D006", "department_name": "行政部", "budget_amount": 200000.0},
    ]

    for dept in departments:
        existing = db.query(DepartmentBudget).filter_by(department_id=dept["department_id"]).first()
        if not existing:
            budget = DepartmentBudget(
                department_id=dept["department_id"],
                department_name=dept["department_name"],
                budget_amount=dept["budget_amount"],
                spent_amount=0.0,
                remaining_amount=dept["budget_amount"]
            )
            db.add(budget)
    db.commit()
    print("Department budget data seeded")


def seed_users(db: Session):
    if db.query(User).count() > 0:
        print("Users already exist, skipping")
        return

    password = hash_password("123456")

    employees = [
        {"user_id": "E001", "username": "zhangsan", "name": "张三", "department_id": "D001", "email": "434226905@qq.com"},
        {"user_id": "E002", "username": "lisi", "name": "李四", "department_id": "D002", "email": "lisi@example.com"},
        {"user_id": "E003", "username": "wangwu", "name": "王五", "department_id": "D003", "email": "wangwu@example.com"},
        {"user_id": "E004", "username": "zhaoliu", "name": "赵六", "department_id": "D004", "email": "zhaoliu@example.com"},
        {"user_id": "E005", "username": "qianqi", "name": "钱七", "department_id": "D005", "email": "qianqi@example.com"},
        {"user_id": "E006", "username": "zhousan", "name": "周芳", "department_id": "D006", "email": "zhousan@example.com"},
    ]

    managers = [
        # D001 技术部
        {"user_id": "S001", "username": "sunjl", "name": "孙经理", "department_id": "D001", "email": "434226905@qq.com"},
        # D002 市场部
        {"user_id": "M001", "username": "majl", "name": "马经理", "department_id": "D002", "email": "yin_20041128@qq.com"},
        # D003 财务部
        {"user_id": "F001", "username": "fangjl", "name": "方经理", "department_id": "D003", "email": "fangjl@example.com"},
        # D004 人力资源部
        {"user_id": "H001", "username": "hejl", "name": "何经理", "department_id": "D004", "email": "hejl@example.com"},
        # D005 销售部
        {"user_id": "X001", "username": "xiangjl", "name": "项经理", "department_id": "D005", "email": "xiangjl@example.com"},
        # D006 行政部
        {"user_id": "G001", "username": "guojl", "name": "郭经理", "department_id": "D006", "email": "guojl@example.com"},
    ]

    directors = [
        # D001 技术部
        {"user_id": "S002", "username": "shenzj", "name": "沈总监", "department_id": "D001", "email": "2081415890@qq.com"},
        # D002 市场部
        {"user_id": "M002", "username": "miaozj", "name": "苗总监", "department_id": "D002", "email": "miaozj@example.com"},
        # D003 财务部
        {"user_id": "F002", "username": "fanzj", "name": "范总监", "department_id": "D003", "email": "fanzj@example.com"},
        # D004 人力资源部
        {"user_id": "H002", "username": "hezj", "name": "贺总监", "department_id": "D004", "email": "hezj@example.com"},
        # D005 销售部
        {"user_id": "X002", "username": "xiezj", "name": "谢总监", "department_id": "D005", "email": "xiezj@example.com"},
        # D006 行政部
        {"user_id": "G002", "username": "gaozj", "name": "高总监", "department_id": "D006", "email": "gaozj@example.com"},
    ]

    general_managers = [
        {"user_id": "A003", "username": "wufz", "name": "吴总经理", "department_id": None, "email": "2081415890@qq.com"},
    ]

    for emp in employees:
        db.add(User(
            user_id=emp["user_id"], username=emp["username"],
            password_hash=password, role="employee", name=emp["name"],
            email=emp["email"], department_id=emp["department_id"],
        ))

    for mgr in managers:
        db.add(User(
            user_id=mgr["user_id"], username=mgr["username"],
            password_hash=password, role="manager", name=mgr["name"],
            email=mgr["email"], department_id=mgr["department_id"],
        ))

    for dir_ in directors:
        db.add(User(
            user_id=dir_["user_id"], username=dir_["username"],
            password_hash=password, role="director", name=dir_["name"],
            email=dir_["email"], department_id=dir_["department_id"],
        ))

    for gm in general_managers:
        db.add(User(
            user_id=gm["user_id"], username=gm["username"],
            password_hash=password, role="general_manager", name=gm["name"],
            email=gm["email"], department_id=gm["department_id"],
        ))

    # 管理员
    db.add(User(
        user_id="ADMIN", username="admin",
        password_hash=hash_password("admin123"), role="admin",
        name="系统管理员", email="admin@example.com", department_id=None,
    ))

    db.commit()
    print("Users data seeded")


def seed_department_approvers(db: Session):
    if db.query(DepartmentApprover).count() > 0:
        print("Department approvers already exist, skipping")
        return

    approvers = [
        # D001 技术部
        {"department_id": "D001", "approval_level": 1, "approver_id": "S001", "approver_name": "孙经理"},
        {"department_id": "D001", "approval_level": 2, "approver_id": "S002", "approver_name": "沈总监"},
        {"department_id": "D001", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
        # D002 市场部
        {"department_id": "D002", "approval_level": 1, "approver_id": "M001", "approver_name": "马经理"},
        {"department_id": "D002", "approval_level": 2, "approver_id": "M002", "approver_name": "苗总监"},
        {"department_id": "D002", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
        # D003 财务部
        {"department_id": "D003", "approval_level": 1, "approver_id": "F001", "approver_name": "方经理"},
        {"department_id": "D003", "approval_level": 2, "approver_id": "F002", "approver_name": "范总监"},
        {"department_id": "D003", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
        # D004 人力资源部
        {"department_id": "D004", "approval_level": 1, "approver_id": "H001", "approver_name": "何经理"},
        {"department_id": "D004", "approval_level": 2, "approver_id": "H002", "approver_name": "贺总监"},
        {"department_id": "D004", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
        # D005 销售部
        {"department_id": "D005", "approval_level": 1, "approver_id": "X001", "approver_name": "项经理"},
        {"department_id": "D005", "approval_level": 2, "approver_id": "X002", "approver_name": "谢总监"},
        {"department_id": "D005", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
        # D006 行政部
        {"department_id": "D006", "approval_level": 1, "approver_id": "G001", "approver_name": "郭经理"},
        {"department_id": "D006", "approval_level": 2, "approver_id": "G002", "approver_name": "高总监"},
        {"department_id": "D006", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
    ]

    for a in approvers:
        db.add(DepartmentApprover(**a))
    db.commit()
    print("Department approvers data seeded")


def seed_reimbursements(db: Session):
    statuses = ["pending", "reviewing", "approved", "rejected"]
    expense_types = ["差旅费", "业务招待费", "办公用品", "日常交通费", "其他费用"]
    employees = [
        ("E001", "张三", "D001"),
        ("E002", "李四", "D002"),
        ("E003", "王五", "D003"),
        ("E004", "赵六", "D004"),
        ("E005", "钱七", "D005"),
    ]

    existing_count = db.query(Reimbursements).count()
    if existing_count > 0:
        print("Reimbursement data already exists, skipping")
        return

    # 员工邮箱映射
    emp_emails = {
        "E001": "434226905@qq.com",
        "E002": "lisi@example.com",
        "E003": "wangwu@example.com",
        "E004": "zhaoliu@example.com",
        "E005": "qianqi@example.com",
    }

    for i in range(15):
        emp_id, emp_name, dept_id = random.choice(employees)
        amount = round(random.uniform(100, 5000), 2)
        status = random.choice(statuses)
        created_date = datetime.now() - timedelta(days=random.randint(1, 30))
        inv_type = random.choice(["增值税发票", "出租车票", "火车票"])
        inv_code = f"INV{random.randint(10000,99999)}"

        reimbursement = Reimbursements(
            reimbursement_no=f"RB{datetime.now().year}{str(i+1).zfill(4)}",
            employee_id=emp_id,
            employee_name=emp_name,
            department_id=dept_id,
            expense_type=random.choice(expense_types),
            total_amount=amount,
            description=f"报销{random.choice(expense_types)}",
            status=status,
            need_special_approval=amount > 10000,
            invoice_details=json.dumps([{
                "type_name": inv_type,
                "amount": amount,
                "invoice_code": inv_code,
                "seller_name": "示例销售方"
            }], ensure_ascii=False),
            applicant_email=emp_emails.get(emp_id),
            created_at=created_date,
            updated_at=created_date
        )
        db.add(reimbursement)
        db.flush()  # 获取reimbursement.id

        # 同时创建Invoice记录并关联
        db.add(Invoice(
            invoice_code=inv_code,
            invoice_number=f"NUM{random.randint(100000,999999)}",
            invoice_type="vat_invoice" if inv_type == "增值税发票" else "taxi_receipt",
            invoice_type_name=inv_type,
            amount=amount,
            invoice_date=created_date.strftime("%Y年%m月%d日"),
            seller_name="示例销售方",
            seller_tax_id="91110000MA01ABCD",
            buyer_name="示例公司",
            buyer_tax_id="91110000MA01EFGH",
            confidence="0.9500",
            uploaded_by=emp_id,
            reimbursement_id=reimbursement.id,
            reimbursement_no=reimbursement.reimbursement_no,
            created_at=created_date,
            updated_at=created_date,
        ))
    db.commit()
    print("Reimbursement data seeded")


def seed_approval_records(db: Session):
    reimbursements = db.query(Reimbursements).all()

    for reimbursement in reimbursements:
        existing = db.query(ApprovalRecords).filter_by(reimbursement_id=reimbursement.id).count()
        if existing > 0:
            continue

        # 查询该部门的审批人
        dept_approvers = db.query(DepartmentApprover).filter_by(
            department_id=reimbursement.department_id
        ).order_by(DepartmentApprover.approval_level).all()

        if not dept_approvers:
            continue

        amount = reimbursement.total_amount
        if amount < 2000:
            levels = 1
        elif amount < 10000:
            levels = 2
        else:
            levels = 3

        for level in range(1, levels + 1):
            approver = next((a for a in dept_approvers if a.approval_level == level), None)
            if not approver:
                continue

            status = random.choice(["approved", "approved", "approved", "pending"]) if level < levels else "pending"

            if reimbursement.status == "approved":
                status = "approved"
            elif reimbursement.status == "rejected":
                status = "rejected" if level == 1 else "pending"

            record = ApprovalRecords(
                reimbursement_id=reimbursement.id,
                approver_id=approver.approver_id,
                approver_name=approver.approver_name,
                approval_level=level,
                status=status,
                comment="同意" if status == "approved" else ("驳回" if status == "rejected" else "待审批"),
                approved_at=datetime.now() - timedelta(hours=random.randint(1, 48)) if status != "pending" else None
            )
            db.add(record)
    db.commit()
    print("Approval records data seeded")


def update_budget_spent(db: Session):
    departments = db.query(DepartmentBudget).all()
    for dept in departments:
        spent = db.query(func.sum(Reimbursements.total_amount)).filter(
            Reimbursements.department_id == dept.department_id,
            Reimbursements.status == "approved"
        ).scalar() or 0.0
        dept.spent_amount = spent
        dept.remaining_amount = dept.budget_amount - spent
    db.commit()
    print("Budget spent amounts updated")


def main():
    from src.db.database import SessionLocal
    db = SessionLocal()
    try:
        seed_department_budget(db)
        seed_users(db)
        seed_department_approvers(db)
        seed_reimbursements(db)
        seed_approval_records(db)
        update_budget_spent(db)
        print("All data seeded successfully")
    finally:
        db.close()


if __name__ == "__main__":
    main()
