from langchain.tools import tool
from src.db.database import SessionLocal
from src.db.models import Reimbursements, DepartmentApprover, ApprovalRecords, User
from datetime import datetime


@tool("创建报销单")
def create_reimbursement(
    employee_id: str,
    employee_name: str,
    department_id: str,
    expense_type: str,
    total_amount: float,
    description: str = "",
    invoice_details_json: str = "[]",
    applicant_email: str = ""
) -> str:
    """
    创建一条新的报销记录并存入数据库，返回报销单号
    :param employee_id: 员工ID，如 E001
    :param employee_name: 员工姓名
    :param department_id: 部门ID，如 D001-D005
    :param expense_type: 费用类型，如 差旅费、招待费、办公用品、交通费、通讯费
    :param total_amount: 报销总金额（元）
    :param description: 报销说明（可选）
    :param invoice_details_json: 发票OCR结果的JSON数组字符串（可选）
    :param applicant_email: 申请人邮箱（可选，用于审批通知）
    """
    db = SessionLocal()
    try:
        year = datetime.now().strftime("%Y")
        last_record = db.query(Reimbursements).filter(
            Reimbursements.reimbursement_no.like(f"RB{year}%")
        ).order_by(Reimbursements.id.desc()).first()

        next_seq = 1
        if last_record:
            try:
                last_seq = int(last_record.reimbursement_no[-4:])
                next_seq = last_seq + 1
            except (ValueError, IndexError):
                pass

        reimbursement_no = f"RB{year}{str(next_seq).zfill(4)}"
        need_special_approval = total_amount > 3000

        # 自动从User表获取申请人邮箱
        if not applicant_email:
            user = db.query(User).filter_by(user_id=employee_id).first()
            if user and user.email:
                applicant_email = user.email

        record = Reimbursements(
            reimbursement_no=reimbursement_no,
            employee_id=employee_id,
            employee_name=employee_name,
            department_id=department_id,
            expense_type=expense_type,
            total_amount=total_amount,
            description=description,
            status="draft",
            need_special_approval=need_special_approval,
            invoice_details=invoice_details_json,
            applicant_email=applicant_email or None,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(record)
        db.commit()

        special_note = "（需特殊审批）" if need_special_approval else ""
        return (
            f"报销单创建成功！\n"
            f"报销单号：{reimbursement_no}\n"
            f"员工：{employee_name}（{employee_id}）\n"
            f"部门：{department_id}\n"
            f"费用类型：{expense_type}\n"
            f"金额：{total_amount:,.2f} 元{special_note}\n"
            f"状态：草稿\n"
            f"请记住报销单号 {reimbursement_no}，接下来需要提交审批。\n"
            f"[[进度查询]]"
        )
    except Exception as e:
        db.rollback()
        return f"创建报销单失败：{str(e)}"
    finally:
        db.close()


@tool("提交审批")
def submit_for_approval(reimbursement_no: str) -> str:
    """
    将草稿或已驳回的报销单提交至审批流程
    :param reimbursement_no: 报销单号，如 RB20260016
    """
    db = SessionLocal()
    try:
        reimbursement = db.query(Reimbursements).filter_by(
            reimbursement_no=reimbursement_no
        ).first()

        if not reimbursement:
            return f"错误：未找到报销单号为 {reimbursement_no} 的记录"

        if reimbursement.status not in ("draft", "rejected"):
            return f"错误：报销单 {reimbursement_no} 当前状态为「{reimbursement.status}」，无法提交审批。只有草稿或已驳回状态可以提交"

        reimbursement.status = "pending"
        reimbursement.updated_at = datetime.now()

        # 从 department_approvers 表查询该部门的审批人
        dept_approvers = db.query(DepartmentApprover).filter_by(
            department_id=reimbursement.department_id
        ).order_by(DepartmentApprover.approval_level).all()

        if not dept_approvers:
            return f"错误：部门 {reimbursement.department_id} 未配置审批人，请联系管理员"

        amount = reimbursement.total_amount
        if amount <= 1000:
            levels = 1
        elif amount <= 3000:
            levels = 2
        else:
            levels = 3

        created_levels = []
        for level in range(1, levels + 1):
            approver = next((a for a in dept_approvers if a.approval_level == level), None)
            if not approver:
                return f"错误：部门 {reimbursement.department_id} 未配置第 {level} 级审批人"

            existing = db.query(ApprovalRecords).filter_by(
                reimbursement_id=reimbursement.id,
                approval_level=level
            ).first()

            if not existing:
                record = ApprovalRecords(
                    reimbursement_id=reimbursement.id,
                    approver_id=approver.approver_id,
                    approver_name=approver.approver_name,
                    approval_level=level,
                    status="pending",
                    comment="待审批"
                )
                db.add(record)
                created_levels.append(f"第{level}级审批人：{approver.approver_name}（{approver.approver_id}）")
            else:
                existing.status = "pending"
                existing.comment = "待审批"
                existing.approver_id = approver.approver_id
                existing.approver_name = approver.approver_name
                created_levels.append(f"第{level}级审批人：{approver.approver_name}（{approver.approver_id}）[已重置]")

        db.commit()

        levels_text = "\n".join(created_levels)
        return (
            f"报销单 {reimbursement_no} 已成功提交审批！\n"
            f"审批层级：共 {levels} 级\n"
            f"{levels_text}\n"
            f"当前状态：待审批\n"
            f"[[模拟审批]]"
        )
    except Exception as e:
        db.rollback()
        return f"提交审批失败：{str(e)}"
    finally:
        db.close()
