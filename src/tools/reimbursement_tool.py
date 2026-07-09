from langchain.tools import tool
from src.db.database import SessionLocal
from src.db.models import Reimbursements, DepartmentApprover, ApprovalRecords, User, Invoice, Voucher
from datetime import datetime


@tool("创建报销单")
def create_reimbursement(
    employee_id: str,
    employee_name: str,
    department_id: str,
    expense_type: str,
    invoice_ids: str,
    description: str = "",
    invoice_details_json: str = "[]",
    applicant_email: str = "",
    voucher_ids: str = ""
) -> str:
    """
    创建一条新的报销记录并存入数据库，返回报销单号
    :param employee_id: 员工ID，如 E001
    :param employee_name: 员工姓名
    :param department_id: 部门ID，如 D001-D005
    :param expense_type: 费用类型，如 差旅费、招待费、办公用品、交通费、通讯费
    :param invoice_ids: 发票记录ID列表，用逗号分隔（必填，如"1,2,3"，关联Invoice表中的发票）
    :param description: 报销说明（可选）
    :param invoice_details_json: 发票OCR结果的JSON数组字符串（可选）
    :param applicant_email: 申请人邮箱（可选，用于审批通知）
    :param voucher_ids: 凭证记录ID列表，用逗号分隔（可选，如"1,2"，关联Voucher表中的凭证）
    """
    db = SessionLocal()
    try:
        if not invoice_ids.strip():
            return "错误：发票ID列表不能为空"
        
        id_list = [int(x.strip()) for x in invoice_ids.split(",") if x.strip()]
        
        # 发票重复报销校验
        for inv_id in id_list:
            inv = db.query(Invoice).filter_by(id=inv_id).first()
            if inv and inv.reimbursement_id is not None:
                return f"错误：发票记录ID {inv_id}（{inv.invoice_type_name}，{inv.amount:,.2f}元）已关联报销单 {inv.reimbursement_no}，不可重复报销"
        
        # 查询所有发票并计算合规金额
        valid_invoices = []
        invalid_invoices = []
        for inv_id in id_list:
            inv = db.query(Invoice).filter_by(id=inv_id).first()
            if inv:
                if inv.is_valid:
                    valid_invoices.append(inv)
                else:
                    invalid_invoices.append(inv)
        
        # 如果没有合规发票，拒绝创建报销单
        if not valid_invoices:
            invalid_reasons = "\n".join([f"  - 发票ID {inv.id}：{inv.invalid_reason or '未标记为合规'}" for inv in invalid_invoices])
            return f"错误：所选发票中没有合规的发票，无法创建报销单。\n不合规原因：\n{invalid_reasons}"
        
        # 计算合规发票总金额
        total_amount = sum(inv.amount for inv in valid_invoices)

        # 查询并累加凭证金额
        voucher_list = []
        voucher_amount = 0.0
        if voucher_ids and voucher_ids.strip():
            vid_list = [int(x.strip()) for x in voucher_ids.split(",") if x.strip()]
            for vid in vid_list:
                v = db.query(Voucher).filter_by(id=vid).first()
                if v:
                    if v.reimbursement_id is not None:
                        return f"错误：凭证记录ID {vid}已关联报销单 {v.reimbursement_no}，不可重复报销"
                    voucher_list.append(v)
                    voucher_amount += v.amount or 0
            total_amount += voucher_amount

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
        db.refresh(record)

        # 关联所有发票记录（包括不合规的，用于留痕）
        linked_count = 0
        for inv_id in id_list:
            inv = db.query(Invoice).filter_by(id=inv_id).first()
            if inv:
                inv.reimbursement_id = record.id
                inv.reimbursement_no = reimbursement_no
                linked_count += 1
        db.commit()

        # 关联凭证记录
        linked_voucher_count = 0
        for v in voucher_list:
            v.reimbursement_id = record.id
            v.reimbursement_no = reimbursement_no
            linked_voucher_count += 1
        db.commit()

        special_note = "（需特殊审批）" if need_special_approval else ""
        invoice_note = f"\n已关联 {linked_count} 张发票记录（合规 {len(valid_invoices)} 张，不合规 {len(invalid_invoices)} 张）" if linked_count > 0 else ""
        voucher_note = f"\n已关联 {linked_voucher_count} 张凭证记录（金额 {voucher_amount:,.2f} 元）" if linked_voucher_count > 0 else ""
        
        result = (
            f"报销单创建成功！\n"
            f"报销单号：{reimbursement_no}\n"
            f"员工：{employee_name}（{employee_id}）\n"
            f"部门：{department_id}\n"
            f"费用类型：{expense_type}\n"
            f"金额：{total_amount:,.2f} 元{special_note}\n"
            f"状态：草稿{invoice_note}{voucher_note}\n"
        )
        
        if invalid_invoices:
            result += f"不合规发票明细：\n"
            for inv in invalid_invoices:
                result += f"  - 发票ID {inv.id}：{inv.invalid_reason}\n"
        
        result += f"请记住报销单号 {reimbursement_no}，接下来需要提交审批。\n[[进度查询]]"
        
        return result
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
