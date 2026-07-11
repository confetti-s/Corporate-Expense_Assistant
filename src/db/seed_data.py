from sqlalchemy.orm import Session
from sqlalchemy import func
from src.db.models import Reimbursements, DepartmentBudget, ApprovalRecords, User, DepartmentApprover, Invoice, Voucher
from src.db.auth import hash_password
from datetime import datetime, timedelta
import json

# 五大费用类型
EXPENSE_TYPES = ["差旅费", "业务招待费", "日常交通费", "办公用品", "其他费用"]


def seed_department_budget(db: Session):
    """每个部门每个费用类别一行预算"""
    departments = [
        {"department_id": "D001", "department_name": "技术部",
         "budgets": {"差旅费": 150000, "业务招待费": 80000, "日常交通费": 50000, "办公用品": 120000, "其他费用": 100000}},
        {"department_id": "D002", "department_name": "市场部",
         "budgets": {"差旅费": 80000, "业务招待费": 100000, "日常交通费": 40000, "办公用品": 30000, "其他费用": 50000}},
        {"department_id": "D003", "department_name": "财务部",
         "budgets": {"差旅费": 20000, "业务招待费": 15000, "日常交通费": 20000, "办公用品": 25000, "其他费用": 20000}},
        {"department_id": "D004", "department_name": "人力资源部",
         "budgets": {"差旅费": 15000, "业务招待费": 20000, "日常交通费": 15000, "办公用品": 15000, "其他费用": 15000}},
        {"department_id": "D005", "department_name": "销售部",
         "budgets": {"差旅费": 250000, "业务招待费": 300000, "日常交通费": 100000, "办公用品": 50000, "其他费用": 100000}},
        {"department_id": "D006", "department_name": "行政部",
         "budgets": {"差旅费": 20000, "业务招待费": 30000, "日常交通费": 30000, "办公用品": 80000, "其他费用": 40000}},
    ]

    for dept in departments:
        for etype in EXPENSE_TYPES:
            existing = db.query(DepartmentBudget).filter_by(
                department_id=dept["department_id"], expense_type=etype
            ).first()
            if not existing:
                budget_amount = dept["budgets"][etype]
                db.add(DepartmentBudget(
                    department_id=dept["department_id"],
                    department_name=dept["department_name"],
                    expense_type=etype,
                    budget_amount=budget_amount,
                    spent_amount=0.0,
                    remaining_amount=budget_amount,
                ))
    db.commit()
    print("Department budget data seeded (by category)")


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
        {"user_id": "S001", "username": "sunjl", "name": "孙经理", "department_id": "D001", "email": "434226905@qq.com"},
        {"user_id": "M001", "username": "majl", "name": "马经理", "department_id": "D002", "email": "yin_20041128@qq.com"},
        {"user_id": "F001", "username": "fangjl", "name": "方经理", "department_id": "D003", "email": "fangjl@example.com"},
        {"user_id": "H001", "username": "hejl", "name": "何经理", "department_id": "D004", "email": "hejl@example.com"},
        {"user_id": "X001", "username": "xiangjl", "name": "项经理", "department_id": "D005", "email": "xiangjl@example.com"},
        {"user_id": "G001", "username": "guojl", "name": "郭经理", "department_id": "D006", "email": "guojl@example.com"},
    ]

    directors = [
        {"user_id": "S002", "username": "shenzj", "name": "沈总监", "department_id": "D001", "email": "2081415890@qq.com"},
        {"user_id": "M002", "username": "miaozj", "name": "苗总监", "department_id": "D002", "email": "miaozj@example.com"},
        {"user_id": "F002", "username": "fanzj", "name": "范总监", "department_id": "D003", "email": "fanzj@example.com"},
        {"user_id": "H002", "username": "hezj", "name": "贺总监", "department_id": "D004", "email": "hezj@example.com"},
        {"user_id": "X002", "username": "xiezj", "name": "谢总监", "department_id": "D005", "email": "xiezj@example.com"},
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
        {"department_id": "D001", "approval_level": 1, "approver_id": "S001", "approver_name": "孙经理"},
        {"department_id": "D001", "approval_level": 2, "approver_id": "S002", "approver_name": "沈总监"},
        {"department_id": "D001", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
        {"department_id": "D002", "approval_level": 1, "approver_id": "M001", "approver_name": "马经理"},
        {"department_id": "D002", "approval_level": 2, "approver_id": "M002", "approver_name": "苗总监"},
        {"department_id": "D002", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
        {"department_id": "D003", "approval_level": 1, "approver_id": "F001", "approver_name": "方经理"},
        {"department_id": "D003", "approval_level": 2, "approver_id": "F002", "approver_name": "范总监"},
        {"department_id": "D003", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
        {"department_id": "D004", "approval_level": 1, "approver_id": "H001", "approver_name": "何经理"},
        {"department_id": "D004", "approval_level": 2, "approver_id": "H002", "approver_name": "贺总监"},
        {"department_id": "D004", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
        {"department_id": "D005", "approval_level": 1, "approver_id": "X001", "approver_name": "项经理"},
        {"department_id": "D005", "approval_level": 2, "approver_id": "X002", "approver_name": "谢总监"},
        {"department_id": "D005", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
        {"department_id": "D006", "approval_level": 1, "approver_id": "G001", "approver_name": "郭经理"},
        {"department_id": "D006", "approval_level": 2, "approver_id": "G002", "approver_name": "高总监"},
        {"department_id": "D006", "approval_level": 3, "approver_id": "A003", "approver_name": "吴总经理"},
    ]

    for a in approvers:
        db.add(DepartmentApprover(**a))
    db.commit()
    print("Department approvers data seeded")


# 发票和凭证模板数据，用于创建真实的种子报销记录
_SEED_DATA = [
    # 2026年1月
    {"month": 1, "emp": ("E001", "张三", "D001"), "etype": "差旅费", "amount": 1580.00,
     "desc": "出差北京，高铁往返+住宿2晚", "sub": "出差交通",
     "inv_code": "264420000101", "inv_num": "10001001", "seller": "中国铁路12306", "inv_type": "增值税发票"},
    {"month": 1, "emp": ("E002", "李四", "D002"), "etype": "业务招待费", "amount": 460.00,
     "desc": "招待客户2人，项目洽谈", "sub": "餐饮",
     "inv_code": "264420000102", "inv_num": "10001002", "seller": "广州餐饮管理有限公司", "inv_type": "增值税发票"},
    {"month": 1, "emp": ("E005", "钱七", "D005"), "etype": "差旅费", "amount": 2350.00,
     "desc": "出差上海，机票+住宿3晚", "sub": "出差交通",
     "inv_code": "263120000101", "inv_num": "10001003", "seller": "东方航空", "inv_type": "增值税发票"},
    # 2026年2月
    {"month": 2, "emp": ("E001", "张三", "D001"), "etype": "日常交通费", "amount": 86.50,
     "desc": "拜访客户，公司→南金集团", "sub": "市内公务交通",
     "voucher": True, "payee": "花小猪科技发展有限公司"},
    {"month": 2, "emp": ("E003", "王五", "D003"), "etype": "办公用品", "amount": 320.00,
     "desc": "打印纸、墨盒采购", "sub": "办公用品",
     "inv_code": "264420000201", "inv_num": "10002001", "seller": "济南办公用品有限公司", "inv_type": "增值税发票"},
    {"month": 2, "emp": ("E006", "周芳", "D006"), "etype": "办公用品", "amount": 1580.00,
     "desc": "办公电脑采购2台", "sub": "办公用品",
     "inv_code": "264420000202", "inv_num": "10002002", "seller": "联想信息技术有限公司", "inv_type": "增值税发票"},
    {"month": 2, "emp": ("E005", "钱七", "D005"), "etype": "业务招待费", "amount": 720.00,
     "desc": "招待客户3人，合同签约", "sub": "餐饮",
     "inv_code": "264420000203", "inv_num": "10002003", "seller": "济南舜和国际酒店", "inv_type": "增值税发票"},
    # 2026年3月
    {"month": 3, "emp": ("E002", "李四", "D002"), "etype": "差旅费", "amount": 980.00,
     "desc": "出差深圳，高铁+住宿1晚", "sub": "出差交通",
     "inv_code": "264420000301", "inv_num": "10003001", "seller": "中国铁路12306", "inv_type": "增值税发票"},
    {"month": 3, "emp": ("E004", "赵六", "D004"), "etype": "日常交通费", "amount": 45.00,
     "desc": "社保局办事，公司→人社局", "sub": "市内公务交通",
     "voucher": True, "payee": "滴滴出行科技有限公司"},
    {"month": 3, "emp": ("E001", "张三", "D001"), "etype": "业务招待费", "amount": 295.00,
     "desc": "招待客户2人，项目洽谈", "sub": "餐饮",
     "inv_code": "264420000302", "inv_num": "10003002", "seller": "广州粤色满园餐饮管理有限公司", "inv_type": "增值税发票"},
    {"month": 3, "emp": ("E005", "钱七", "D005"), "etype": "差旅费", "amount": 3200.00,
     "desc": "出差广州，机票+住宿4晚", "sub": "住宿",
     "inv_code": "263120000302", "inv_num": "10003003", "seller": "广州天河希尔顿酒店", "inv_type": "增值税发票"},
    # 2026年4月
    {"month": 4, "emp": ("E003", "王五", "D003"), "etype": "其他费用", "amount": 58.00,
     "desc": "合同快递费", "sub": "快递",
     "voucher": True, "payee": "顺丰速运有限公司"},
    {"month": 4, "emp": ("E006", "周芳", "D006"), "etype": "办公用品", "amount": 650.00,
     "desc": "办公文具、文件夹采购", "sub": "办公用品",
     "inv_code": "264420000401", "inv_num": "10004001", "seller": "得力集团有限公司", "inv_type": "增值税发票"},
    {"month": 4, "emp": ("E002", "李四", "D002"), "etype": "业务招待费", "amount": 1200.00,
     "desc": "招待客户4人，年度合作洽谈", "sub": "餐饮",
     "inv_code": "264420000402", "inv_num": "10004002", "seller": "济南鲁能贵和洲际酒店", "inv_type": "增值税发票"},
    {"month": 4, "emp": ("E001", "张三", "D001"), "etype": "差旅费", "amount": 1860.00,
     "desc": "出差杭州，高铁+住宿2晚", "sub": "住宿",
     "inv_code": "263120000401", "inv_num": "10004003", "seller": "杭州西湖国宾馆", "inv_type": "增值税发票"},
    # 2026年5月
    {"month": 5, "emp": ("E005", "钱七", "D005"), "etype": "业务招待费", "amount": 550.00,
     "desc": "招待客户2人，产品演示", "sub": "餐饮",
     "inv_code": "264420000501", "inv_num": "10005001", "seller": "海底捞餐饮股份有限公司", "inv_type": "增值税发票"},
    {"month": 5, "emp": ("E004", "赵六", "D004"), "etype": "日常交通费", "amount": 120.00,
     "desc": "招聘会交通，公司→国际会展中心", "sub": "市内公务交通",
     "voucher": True, "payee": "高德软件有限公司"},
    {"month": 5, "emp": ("E001", "张三", "D001"), "etype": "其他费用", "amount": 200.00,
     "desc": "服务器域名续费", "sub": "其他",
     "inv_code": "264420000502", "inv_num": "10005002", "seller": "阿里云计算有限公司", "inv_type": "增值税发票"},
    {"month": 5, "emp": ("E005", "钱七", "D005"), "etype": "差旅费", "amount": 4500.00,
     "desc": "出差成都，机票+住宿5晚", "sub": "出差交通",
     "inv_code": "263120000501", "inv_num": "10005003", "seller": "四川航空", "inv_type": "增值税发票"},
    {"month": 5, "emp": ("E002", "李四", "D002"), "etype": "日常交通费", "amount": 35.00,
     "desc": "客户拜访，公司→万达广场", "sub": "市内公务交通",
     "voucher": True, "payee": "滴滴出行科技有限公司"},
    # 2026年6月
    {"month": 6, "emp": ("E003", "王五", "D003"), "etype": "差旅费", "amount": 760.00,
     "desc": "出差青岛，高铁+住宿1晚", "sub": "出差交通",
     "inv_code": "264420000601", "inv_num": "10006001", "seller": "中国铁路12306", "inv_type": "增值税发票"},
    {"month": 6, "emp": ("E006", "周芳", "D006"), "etype": "办公用品", "amount": 2200.00,
     "desc": "打印机采购1台", "sub": "办公用品",
     "inv_code": "264420000602", "inv_num": "10006002", "seller": "惠普中国有限公司", "inv_type": "增值税发票"},
    {"month": 6, "emp": ("E001", "张三", "D001"), "etype": "业务招待费", "amount": 380.00,
     "desc": "招待客户1人，技术交流", "sub": "餐饮",
     "inv_code": "264420000603", "inv_num": "10006003", "seller": "济南趵突泉啤酒有限公司", "inv_type": "增值税发票"},
    {"month": 6, "emp": ("E005", "钱七", "D005"), "etype": "日常交通费", "amount": 92.00,
     "desc": "机场接客户，公司→T3航站楼", "sub": "市内公务交通",
     "voucher": True, "payee": "首汽约车科技有限公司"},
    {"month": 6, "emp": ("E004", "赵六", "D004"), "etype": "其他费用", "amount": 150.00,
     "desc": "员工体检组织费", "sub": "其他",
     "inv_code": "264420000604", "inv_num": "10006004", "seller": "济南市中心医院", "inv_type": "增值税发票"},
    {"month": 6, "emp": ("E002", "李四", "D002"), "etype": "业务招待费", "amount": 880.00,
     "desc": "招待客户3人，市场推广", "sub": "餐饮",
     "inv_code": "264420000605", "inv_num": "10006005", "seller": "济南净雅餐饮管理有限公司", "inv_type": "增值税发票"},
    # 2026年7月
    {"month": 7, "emp": ("E001", "张三", "D001"), "etype": "差旅费", "amount": 2100.00,
     "desc": "出差南京，高铁+住宿3晚", "sub": "住宿",
     "inv_code": "263120000701", "inv_num": "10007001", "seller": "南京金陵饭店", "inv_type": "增值税发票"},
    {"month": 7, "emp": ("E005", "钱七", "D005"), "etype": "业务招待费", "amount": 1650.00,
     "desc": "招待客户5人，战略合作签约", "sub": "餐饮",
     "inv_code": "264420000701", "inv_num": "10007002", "seller": "济南香格里拉大酒店", "inv_type": "增值税发票"},
]


def seed_reimbursements(db: Session):
    existing_count = db.query(Reimbursements).count()
    if existing_count > 0:
        print("Reimbursement data already exists, skipping")
        return

    emp_emails = {
        "E001": "434226905@qq.com",
        "E002": "lisi@example.com",
        "E003": "wangwu@example.com",
        "E004": "zhaoliu@example.com",
        "E005": "qianqi@example.com",
        "E006": "zhousan@example.com",
    }

    for i, item in enumerate(_SEED_DATA):
        emp_id, emp_name, dept_id = item["emp"]
        etype = item["etype"]
        amount = item["amount"]
        created_date = datetime(2026, item["month"], max(1, (i % 28) + 1))

        reimbursement = Reimbursements(
            reimbursement_no=f"RB2026{str(i + 1).zfill(4)}",
            employee_id=emp_id,
            employee_name=emp_name,
            department_id=dept_id,
            expense_type=etype,
            total_amount=amount,
            description=item["desc"],
            status="approved",
            need_special_approval=amount > 10000,
            ai_suggestion="通过",
            applicant_email=emp_emails.get(emp_id),
            created_at=created_date,
            updated_at=created_date,
        )
        db.add(reimbursement)
        db.flush()

        if item.get("voucher"):
            # 凭证类
            db.add(Voucher(
                voucher_type="微信付款截图",
                amount=amount,
                payment_date=created_date.strftime("%Y-%m-%d"),
                payee=item.get("payee", "未知"),
                description=item["desc"],
                sub_expense_type=item["sub"],
                is_valid=True,
                uploaded_by=emp_id,
                reimbursement_id=reimbursement.id,
                reimbursement_no=reimbursement.reimbursement_no,
                created_at=created_date,
                updated_at=created_date,
            ))
        else:
            # 发票类
            db.add(Invoice(
                invoice_code=item["inv_code"],
                invoice_number=item["inv_num"],
                invoice_type="vat_invoice",
                invoice_type_name=item["inv_type"],
                amount=amount,
                invoice_date=created_date.strftime("%Y年%m月%d日"),
                seller_name=item["seller"],
                confidence="0.9500",
                uploaded_by=emp_id,
                sub_expense_type=item["sub"],
                description=item["desc"],
                is_valid=True,
                reimbursement_id=reimbursement.id,
                reimbursement_no=reimbursement.reimbursement_no,
                created_at=created_date,
                updated_at=created_date,
            ))

    db.commit()
    print("Reimbursement data seeded (with dates spanning Jan-Jul 2026)")


def seed_approval_records(db: Session):
    reimbursements = db.query(Reimbursements).all()

    for idx, reimbursement in enumerate(reimbursements):
        existing = db.query(ApprovalRecords).filter_by(reimbursement_id=reimbursement.id).count()
        if existing > 0:
            continue

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

            record = ApprovalRecords(
                reimbursement_id=reimbursement.id,
                approver_id=approver.approver_id,
                approver_name=approver.approver_name,
                approval_level=level,
                status="approved",
                comment="同意",
                approved_at=reimbursement.created_at + timedelta(hours=level * 4 + (idx % 6))
            )
            db.add(record)
    db.commit()
    print("Approval records data seeded")


def update_budget_spent(db: Session):
    """按部门+费用类别更新预算已支出金额"""
    for dept_budget in db.query(DepartmentBudget).all():
        spent = db.query(func.sum(Reimbursements.total_amount)).filter(
            Reimbursements.department_id == dept_budget.department_id,
            Reimbursements.expense_type == dept_budget.expense_type,
            Reimbursements.status == "approved"
        ).scalar() or 0.0
        dept_budget.spent_amount = spent
        dept_budget.remaining_amount = dept_budget.budget_amount - spent
    db.commit()
    print("Budget spent amounts updated (by department + expense_type)")


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
