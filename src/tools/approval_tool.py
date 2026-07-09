from langchain.tools import tool
from src.db.database import SessionLocal
from src.db.models import Reimbursements, ApprovalRecords, DepartmentBudget, User
from datetime import datetime, timedelta
from sqlalchemy import func
from src.tools.budget_tool import update_budget_spent


@tool("查询待审批记录")
def query_pending_approvals(approver_id: str, start_date: str = "", end_date: str = "", applicant_name: str = "") -> str:
    """
    查询审批人待处理的报销单列表，支持按日期范围和申请人姓名筛选
    :param approver_id: 审批人ID（如S001、M001、A003等）
    :param start_date: 开始日期，格式YYYY-MM-DD（可选）
    :param end_date: 结束日期，格式YYYY-MM-DD（可选）
    :param applicant_name: 申请人姓名筛选（可选，模糊匹配）
    :return: 待审批记录列表
    """
    db = SessionLocal()
    try:
        # 查询该审批人的所有待审批记录
        query = db.query(ApprovalRecords).filter_by(
            approver_id=approver_id,
            status="pending"
        )

        records = query.all()
        if not records:
            return f"您当前没有待审批的报销单。"

        # 组装数据并筛选
        data = []
        for rec in records:
            reimb = db.query(Reimbursements).filter_by(id=rec.reimbursement_id).first()
            if not reimb:
                continue
            if reimb.status not in ("pending", "reviewing"):
                continue

            # 前置级别校验
            if rec.approval_level > 1:
                prev_ok = all(
                    db.query(ApprovalRecords).filter_by(
                        reimbursement_id=reimb.id,
                        approval_level=pl
                    ).first().status == "approved"
                    for pl in range(1, rec.approval_level)
                    if db.query(ApprovalRecords).filter_by(
                        reimbursement_id=reimb.id,
                        approval_level=pl
                    ).first()
                )
                if not prev_ok:
                    continue

            # 日期筛选
            if start_date:
                try:
                    sd = datetime.strptime(start_date, '%Y-%m-%d')
                    if reimb.created_at < sd:
                        continue
                except ValueError:
                    pass
            if end_date:
                try:
                    ed = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                    if reimb.created_at > ed:
                        continue
                except ValueError:
                    pass

            # 申请人姓名筛选
            if applicant_name:
                if applicant_name.lower() not in reimb.employee_name.lower():
                    continue

            # 获取部门名称
            dept_name = reimb.department_id
            dept = db.query(DepartmentBudget).filter_by(department_id=reimb.department_id).first()
            if dept:
                dept_name = dept.department_name

            data.append({
                "reimbursement_no": reimb.reimbursement_no,
                "applicant": reimb.employee_name,
                "department": dept_name,
                "amount": reimb.total_amount,
                "expense_type": reimb.expense_type,
                "level": rec.approval_level,
                "created_at": reimb.created_at,
            })

        if not data:
            return f"没有符合条件的待审批记录。"

        # 按提交时间排序
        data.sort(key=lambda x: x["created_at"], reverse=True)

        result = f"📋 **待审批记录（共 {len(data)} 条）**\n\n"
        for i, item in enumerate(data, 1):
            result += f"""**{i}. 报销单号：{item['reimbursement_no']}**
   申请人：{item['applicant']}
   部门：{item['department']}
   金额：{item['amount']:,.2f} 元
   费用类型：{item['expense_type']}
   审批级别：L{item['level']}
   提交时间：{item['created_at'].strftime('%Y-%m-%d %H:%M')}
   状态：等待您审批

"""
        result += "---\n💡 您可以说：\"审批通过 RB20260001\" 或 \"驳回 RB20260002，理由是超标\" 来完成审批操作。"
        return result
    finally:
        db.close()


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

            # 重新查询报销单对象，确保它仍然绑定到会话
            reimbursement = db.query(Reimbursements).filter_by(
                reimbursement_no=reimbursement_no
            ).first()

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

        db.commit()

        # 更新所有部门预算使用情况
        update_budget_spent()

        # 重新查询报销单对象，确保它仍然绑定到会话
        reimbursement = db.query(Reimbursements).filter_by(
            reimbursement_no=reimbursement_no
        ).first()

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
            print(f"[邮件通知] EMAIL_NOTIFICATION_ENABLED=False，跳过发送")
            return
    except Exception:
        return

    to_email = reimbursement.applicant_email
    if not to_email:
        user = db.query(User).filter_by(user_id=reimbursement.employee_id).first()
        if user and user.email:
            to_email = user.email
            print(f"[邮件通知] 从用户表获取申请人邮箱：{to_email}")
        else:
            print(f"[邮件通知] 申请人 {reimbursement.employee_name}({reimbursement.employee_id}) 无邮箱，跳过发送")
            return

    try:
        from src.tools.email_tool import send_email
        action_text = "通过" if action == "approved" else "驳回"
        result = send_email.func(
            to_email=to_email,
            subject=f"报销单{reimbursement.reimbursement_no}审批{action_text}",
            body=(
                f"您的报销单 {reimbursement.reimbursement_no} 已被{action_text}。\n"
                f"审批人：{approver_name}\n"
                f"金额：{reimbursement.total_amount:,.2f} 元\n"
                f"费用类型：{reimbursement.expense_type}\n"
                f"审批意见：{comment or '无'}"
            )
        )
        if "失败" in result:
            print(f"[邮件通知失败] {result}")
        else:
            print(f"[邮件通知成功] 已发送给 {to_email}")
    except Exception as e:
        print(f"[邮件通知失败] {e}")


def _send_next_approver_email(db, reimbursement, next_level):
    """通知下一级审批人"""
    try:
        from config import EMAIL_NOTIFICATION_ENABLED
        if not EMAIL_NOTIFICATION_ENABLED:
            print(f"[邮件通知] EMAIL_NOTIFICATION_ENABLED=False，跳过通知下一级审批人")
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
