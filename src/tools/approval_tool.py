from langchain.tools import tool
from src.db.database import SessionLocal
from src.db.models import Reimbursements, ApprovalRecords, DepartmentBudget, User
from datetime import datetime
from sqlalchemy import func


@tool("执行审批操作")
def approve_or_reject_reimbursement(
    reimbursement_no: str,
    action: str,
    approver_id: str = "",
    comment: str = ""
) -> str:
    """
    对报销单执行审批通过或驳回操作
    :param reimbursement_no: 报销单号
    :param action: 操作类型，"approve" 表示通过，"reject" 表示驳回
    :param approver_id: 审批人ID（如S001、M001、A003等）
    :param comment: 审批意见（可选）
    """
    db = SessionLocal()
    try:
        if action not in ("approve", "reject"):
            return f"错误：无效的操作类型 '{action}'，必须是 'approve' 或 'reject'"

        if not approver_id:
            return "错误：必须提供审批人ID"

        reimbursement = db.query(Reimbursements).filter_by(
            reimbursement_no=reimbursement_no
        ).first()

        if not reimbursement:
            return f"错误：未找到报销单号为 {reimbursement_no} 的记录"

        if reimbursement.status not in ("pending", "reviewing"):
            return f"错误：报销单 {reimbursement_no} 当前状态为「{reimbursement.status}」，无法审批"

        # 从审批记录中找到该审批人对应的待审批记录
        approval_record = db.query(ApprovalRecords).filter_by(
            reimbursement_id=reimbursement.id,
            approver_id=approver_id,
            status="pending"
        ).first()

        if not approval_record:
            return f"错误：未找到审批人 {approver_id} 对报销单 {reimbursement_no} 的待审批记录"

        level = approval_record.approval_level

        # 级别校验：前置级别必须已通过
        if level > 1:
            for prev_level in range(1, level):
                prev_record = db.query(ApprovalRecords).filter_by(
                    reimbursement_id=reimbursement.id,
                    approval_level=prev_level
                ).first()
                if not prev_record or prev_record.status != "approved":
                    return f"错误：第{prev_level}级审批尚未通过，不能跳级审批"

        approval_record.status = "approved" if action == "approve" else "rejected"
        approval_record.comment = comment or ("同意" if action == "approve" else "驳回")
        approval_record.approved_at = datetime.now()

        approver_name = approval_record.approver_name

        if action == "reject":
            reimbursement.status = "rejected"
            reimbursement.updated_at = datetime.now()
            db.commit()

            # 审批驳回后发邮件通知申请人
            _send_notification_email(db, reimbursement, "rejected", approver_name, comment)

            return (
                f"审批结果：报销单 {reimbursement_no} 已被驳回！\n"
                f"审批层级：第{level}级 - {approver_name}\n"
                f"审批意见：{comment or '无'}\n"
                f"报销单状态：已驳回\n"
                f"用户可修改后重新提交。\n"
                f"[[对话报销]]"
            )

        # 通过逻辑
        max_level_record = db.query(ApprovalRecords).filter_by(
            reimbursement_id=reimbursement.id
        ).order_by(ApprovalRecords.approval_level.desc()).first()
        max_level = max_level_record.approval_level if max_level_record else level

        if level < max_level:
            reimbursement.status = "reviewing"
            reimbursement.updated_at = datetime.now()
            db.commit()

            # 通知下一级审批人
            _send_next_approver_email(db, reimbursement, level + 1)

            return (
                f"第{level}级审批通过！\n"
                f"报销单号：{reimbursement_no}\n"
                f"审批人：{approver_name}\n"
                f"当前状态：审批中（等待第{level + 1}级审批）\n"
                f"[[模拟审批]]"
            )

        # 最后一级通过
        reimbursement.status = "approved"
        reimbursement.updated_at = datetime.now()

        # 更新部门预算
        dept = db.query(DepartmentBudget).filter_by(
            department_id=reimbursement.department_id
        ).first()
        if dept:
            approved_total = db.query(func.sum(Reimbursements.total_amount)).filter_by(
                department_id=reimbursement.department_id,
                status="approved"
            ).scalar() or 0
            dept.spent_amount = approved_total
            dept.remaining_amount = dept.budget_amount - approved_total
            dept.updated_at = datetime.now()

        db.commit()

        # 审批通过后发邮件通知申请人
        _send_notification_email(db, reimbursement, "approved", approver_name, comment)

        return (
            f"审批结果：报销单 {reimbursement_no} 全部审批通过！\n"
            f"员工：{reimbursement.employee_name}\n"
            f"金额：{reimbursement.total_amount:,.2f} 元\n"
            f"费用类型：{reimbursement.expense_type}\n"
            f"最终状态：已通过\n"
            f"[[进度查询]]\n"
            f"[[预算看板]]"
        )
    except Exception as e:
        db.rollback()
        return f"审批操作失败：{str(e)}"
    finally:
        db.close()


def _send_notification_email(db, reimbursement, action, approver_name, comment):
    """审批结果通知申请人"""
    try:
        from config import EMAIL_NOTIFICATION_ENABLED
        if not EMAIL_NOTIFICATION_ENABLED:
            return
    except Exception:
        return

    if not reimbursement.applicant_email:
        return

    try:
        from src.tools.email_tool import send_email
        action_text = "通过" if action == "approved" else "驳回"
        send_email.func(
            to_email=reimbursement.applicant_email,
            subject=f"报销单{reimbursement.reimbursement_no}审批{action_text}",
            body=(
                f"您的报销单 {reimbursement.reimbursement_no} 已被{action_text}。\n"
                f"审批人：{approver_name}\n"
                f"金额：{reimbursement.total_amount:,.2f} 元\n"
                f"费用类型：{reimbursement.expense_type}\n"
                f"审批意见：{comment or '无'}"
            )
        )
    except Exception as e:
        print(f"[邮件通知失败] {e}")


def _send_next_approver_email(db, reimbursement, next_level):
    """通知下一级审批人"""
    try:
        from config import EMAIL_NOTIFICATION_ENABLED
        if not EMAIL_NOTIFICATION_ENABLED:
            return
    except Exception:
        return

    try:
        from src.db.models import DepartmentApprover
        next_approver = db.query(DepartmentApprover).filter_by(
            department_id=reimbursement.department_id,
            approval_level=next_level
        ).first()
        if not next_approver:
            return

        approver_user = db.query(User).filter_by(user_id=next_approver.approver_id).first()
        if not approver_user or not approver_user.email:
            return

        from src.tools.email_tool import send_email
        send_email.func(
            to_email=approver_user.email,
            subject=f"待审批：报销单{reimbursement.reimbursement_no}",
            body=(
                f"您有一条新的报销审批待处理。\n"
                f"报销单号：{reimbursement.reimbursement_no}\n"
                f"申请人：{reimbursement.employee_name}\n"
                f"金额：{reimbursement.total_amount:,.2f} 元\n"
                f"费用类型：{reimbursement.expense_type}\n"
                f"审批级别：第{next_level}级"
            )
        )
    except Exception as e:
        print(f"[邮件通知失败] {e}")
