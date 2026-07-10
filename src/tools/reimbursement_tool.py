from langchain.tools import tool
from src.db.database import SessionLocal
from src.db.models import Reimbursements, DepartmentApprover, ApprovalRecords, User, Invoice, Voucher, DepartmentBudget
from src.tools.compliance_tool import compliance_check
from datetime import datetime
from sqlalchemy import func
import json


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
        
        for inv_id in id_list:
            inv = db.query(Invoice).filter_by(id=inv_id).first()
            if inv and inv.reimbursement_id is not None:
                return f"错误：发票记录ID {inv_id}（{inv.invoice_type_name}，{inv.amount:,.2f}元）已关联报销单 {inv.reimbursement_no}，不可重复报销"
        
        COMPANY_POLICY = {
            "差旅费": {"daily_limit": 800},
            "招待费": {"per_person_limit": 300},
            "办公用品": {"single_limit": 5000},
            "交通费": {"daily_limit": 200},
            "通讯费": {"monthly_limit": 500},
            "业务招待费": {"per_person_limit": 300}
        }
        
        for inv_id in id_list:
            inv = db.query(Invoice).filter_by(id=inv_id).first()
            if inv:
                invalid_reason = None

                if not inv.invoice_date:
                    invalid_reason = "缺少开票日期，无法进行时效性校验"
                else:
                    try:
                        invoice_dt = datetime.strptime(inv.invoice_date, "%Y-%m-%d")
                        days_diff = (datetime.now() - invoice_dt).days
                        if days_diff > 90:
                            invalid_reason = f"超过90天有效期（发票日期：{inv.invoice_date}）"
                    except ValueError:
                        try:
                            invoice_dt = datetime.strptime(inv.invoice_date, "%Y年%m月%d日")
                            days_diff = (datetime.now() - invoice_dt).days
                            if days_diff > 90:
                                invalid_reason = f"超过90天有效期（发票日期：{inv.invoice_date}）"
                        except ValueError:
                            invalid_reason = "发票日期格式不正确"

                if not invalid_reason and expense_type in COMPANY_POLICY:
                    policy = COMPANY_POLICY[expense_type]
                    limit_key = list(policy.keys())[0]
                    limit_value = policy[limit_key]
                    if inv.amount > limit_value:
                        invalid_reason = "金额超过合规标准"

                if invalid_reason:
                    inv.is_valid = False
                    inv.invalid_reason = invalid_reason
                else:
                    inv.is_valid = True
                    inv.invalid_reason = None
        db.commit()
        
        valid_invoices = []
        invalid_invoices = []
        for inv_id in id_list:
            inv = db.query(Invoice).filter_by(id=inv_id).first()
            if inv:
                if inv.is_valid:
                    valid_invoices.append(inv)
                else:
                    invalid_invoices.append(inv)
        
        total_amount = sum(inv.amount for inv in valid_invoices) + sum(inv.amount for inv in invalid_invoices)

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

        linked_count = 0
        for inv_id in id_list:
            inv = db.query(Invoice).filter_by(id=inv_id).first()
            if inv:
                inv.reimbursement_id = record.id
                inv.reimbursement_no = reimbursement_no
                linked_count += 1
        db.commit()

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


def _get_next_reimbursement_no(db):
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
    return f"RB{year}{str(next_seq).zfill(4)}"


def _check_budget_internal(db, department_id, amount):
    dept = db.query(DepartmentBudget).filter_by(department_id=department_id).first()
    if not dept:
        return False, "部门预算信息不存在"
    
    spent = db.query(func.sum(Reimbursements.total_amount)).filter(
        Reimbursements.department_id == department_id,
        Reimbursements.status == "approved"
    ).scalar() or 0.0
    
    remaining = dept.budget_amount - spent
    
    if remaining >= amount:
        return True, f"预算充足，剩余 {remaining:,.2f} 元"
    else:
        return False, f"预算不足，剩余 {remaining:,.2f} 元，超出 {amount - remaining:,.2f} 元"


def _determine_expense_type(invoices):
    type_counts = {}
    for inv in invoices:
        if inv.invoice_type_name:
            type_counts[inv.invoice_type_name] = type_counts.get(inv.invoice_type_name, 0) + 1
    
    if not type_counts:
        return "其他"
    
    return max(type_counts, key=type_counts.get)


def _build_invoice_details(invoices):
    details = []
    for inv in invoices:
        details.append({
            "type_name": inv.invoice_type_name or "",
            "amount": inv.amount,
            "invoice_code": inv.invoice_code or "",
            "invoice_number": inv.invoice_number or "",
            "seller_name": inv.seller_name or "",
            "invoice_date": inv.invoice_date or "",
            "file_path": inv.file_path or ""
        })
    return json.dumps(details, ensure_ascii=False)


def _auto_approve_reimbursement(db, reimbursement):
    max_level_record = db.query(ApprovalRecords).filter_by(
        reimbursement_id=reimbursement.id
    ).order_by(ApprovalRecords.approval_level.desc()).first()
    max_level = max_level_record.approval_level if max_level_record else 1
    
    for level in range(1, max_level + 1):
        approval_record = db.query(ApprovalRecords).filter_by(
            reimbursement_id=reimbursement.id,
            approval_level=level
        ).first()
        if approval_record:
            approval_record.status = "approved"
            approval_record.comment = "AI自动审批通过"
            approval_record.approved_at = datetime.now()
    
    reimbursement.status = "approved"
    reimbursement.updated_at = datetime.now()
    
    return True


def _send_ai_approval_email(db, reimbursement_no):
    try:
        from config import EMAIL_NOTIFICATION_ENABLED
        if not EMAIL_NOTIFICATION_ENABLED:
            print(f"[邮件通知] EMAIL_NOTIFICATION_ENABLED=False，跳过发送")
            return
    except Exception:
        return

    reimbursement = db.query(Reimbursements).filter_by(reimbursement_no=reimbursement_no).first()
    if not reimbursement:
        return

    approver_rec = db.query(DepartmentApprover).filter_by(
        department_id=reimbursement.department_id,
        approval_level=1
    ).first()
    if not approver_rec:
        return

    approver_user = db.query(User).filter_by(user_id=approver_rec.approver_id).first()
    if not approver_user or not approver_user.email:
        return

    invoices = db.query(Invoice).filter_by(reimbursement_id=reimbursement.id).all()
    invoice_details = "\n".join([
        f"  - {inv.invoice_type_name}：{inv.amount:,.2f}元（{inv.invoice_date}）"
        for inv in invoices
    ])

    from src.tools.pdf_tool import auto_generate_pdf
    pdf_path = auto_generate_pdf(reimbursement_no)

    from src.tools.email_tool import send_email
    send_email.func(
        to_email=approver_user.email,
        subject=f"【AI自动审批通过】报销单{reimbursement.reimbursement_no}",
        body=(
            f"您好，以下报销单已由AI自动审批通过：\n\n"
            f"报销单号：{reimbursement.reimbursement_no}\n"
            f"申请人：{reimbursement.employee_name}（{reimbursement.employee_id}）\n"
            f"部门：{reimbursement.department_id}\n"
            f"费用类型：{reimbursement.expense_type}\n"
            f"金额：{reimbursement.total_amount:,.2f} 元\n"
            f"审批时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"发票详情：\n{invoice_details}\n\n"
            f"AI决策依据：\n"
            f"  - 所有发票均合规\n"
            f"  - 部门预算充足\n"
            f"  - 金额≤1000元，符合自动审批条件\n\n"
            f"此邮件仅供您知悉，无需额外操作。"
        ),
        attachment_path=pdf_path if pdf_path else None
    )


def _create_approval_records(db, reimbursement):
    dept_approvers = db.query(DepartmentApprover).filter_by(
        department_id=reimbursement.department_id
    ).order_by(DepartmentApprover.approval_level).all()
    
    if not dept_approvers:
        return f"错误：部门 {reimbursement.department_id} 未配置审批人"
    
    amount = reimbursement.total_amount
    if amount <= 1000:
        levels = 1
    elif amount <= 3000:
        levels = 2
    else:
        levels = 3
    
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
    
    return None


def _build_ai_suggestion(db, reimbursement, valid_invoices, invalid_invoices, budget_sufficient, budget_message):
    valid_count = len(valid_invoices)
    invalid_count = len(invalid_invoices)
    total_amount = reimbursement.total_amount if reimbursement else sum(inv.amount for inv in valid_invoices) + sum(inv.amount for inv in invalid_invoices)
    
    if valid_count == 0:
        suggestion = f"【AI建议：驳回】\n理由：\n  - 所有发票均不合规（共{invalid_count}张）\n"
        for inv in invalid_invoices:
            suggestion += f"    * 发票ID{inv.id}：{inv.invalid_reason}\n"
    elif invalid_count == 0 and budget_sufficient:
        if total_amount <= 1000:
            suggestion = f"【AI建议：通过】\n理由：\n  - 所有发票均合规（共{valid_count}张）\n  - 部门预算充足\n  - 金额{total_amount:,.2f}元≤1000元，符合快速审批条件\n"
        else:
            suggestion = f"【AI建议：通过】\n理由：\n  - 所有发票均合规（共{valid_count}张）\n  - 部门预算充足\n  - 金额{total_amount:,.2f}元>1000元，需按金额对应审批级别处理\n"
    elif invalid_count > 0 and budget_sufficient:
        suggestion = f"【AI建议：谨慎审批】\n理由：\n  - 合规发票{valid_count}张，不合规发票{invalid_count}张\n  - 部门预算充足\n  - 建议仔细审核不合规发票的具体原因\n"
        for inv in invalid_invoices:
            suggestion += f"    * 发票ID{inv.id}：{inv.invalid_reason}\n"
    else:
        suggestion = f"【AI建议：谨慎审批】\n理由：\n  - {budget_message}\n  - 合规发票{valid_count}张，不合规发票{invalid_count}张\n"
    
    return suggestion


@tool("查看报销单详情")
def view_reimbursement_detail(reimbursement_no: str) -> str:
    """
    查看报销单详情，以表格形式展示
    :param reimbursement_no: 报销单号，如 RB20260016
    """
    db = SessionLocal()
    try:
        reimbursement = db.query(Reimbursements).filter_by(
            reimbursement_no=reimbursement_no
        ).first()
        
        if not reimbursement:
            return f"错误：未找到报销单号为 {reimbursement_no} 的记录"
        
        invoices = db.query(Invoice).filter_by(reimbursement_id=reimbursement.id).all()
        
        result = f"## 📋 报销单详情\n\n"
        result += f"| 项目 | 内容 |\n"
        result += f"|:---|:---|\n"
        result += f"| 报销单号 | {reimbursement.reimbursement_no} |\n"
        result += f"| 申请人 | {reimbursement.employee_name}（{reimbursement.employee_id}） |\n"
        result += f"| 部门 | {reimbursement.department_id} |\n"
        result += f"| 费用类型 | {reimbursement.expense_type} |\n"
        result += f"| 总金额 | {reimbursement.total_amount:,.2f} 元 |\n"
        result += f"| 报销说明 | {reimbursement.description or '-'} |\n"
        result += f"| 当前状态 | {reimbursement.status} |\n"
        result += f"| 确认状态 | {'✅ 已确认' if reimbursement.confirmed else '❌ 未确认'} |\n"
        result += f"| 创建时间 | {reimbursement.created_at.strftime('%Y-%m-%d %H:%M')} |\n"
        result += f"| 更新时间 | {reimbursement.updated_at.strftime('%Y-%m-%d %H:%M')} |\n"
        
        if invoices:
            result += f"\n### 🧾 发票明细\n\n"
            result += f"| 发票ID | 发票类型 | 金额（元） | 开票日期 | 合规状态 |\n"
            result += f"|:---|:---|:---|:---|:---|\n"
            for inv in invoices:
                status = "✅ 合规" if inv.is_valid else f"❌ {inv.invalid_reason}"
                result += f"| {inv.id} | {inv.invoice_type_name or '未知'} | {inv.amount:,.2f} | {inv.invoice_date or '-'} | {status} |\n"
        
        result += f"\n---\n如需修改报销单信息，请告诉我需要修改的字段和新值；确认无误请回复「确认提交」。"
        
        return result
    except Exception as e:
        return f"查看报销单详情失败：{str(e)}"
    finally:
        db.close()


@tool("更新报销单")
def update_reimbursement(reimbursement_no: str, **kwargs) -> str:
    """
    更新报销单信息
    :param reimbursement_no: 报销单号，如 RB20260016
    :param kwargs: 要更新的字段，如 expense_type, description 等
    """
    db = SessionLocal()
    try:
        reimbursement = db.query(Reimbursements).filter_by(
            reimbursement_no=reimbursement_no
        ).first()
        
        if not reimbursement:
            return f"错误：未找到报销单号为 {reimbursement_no} 的记录"
        
        if reimbursement.status not in ("draft", "rejected"):
            return f"错误：报销单 {reimbursement_no} 当前状态为「{reimbursement.status}」，无法修改"
        
        updatable_fields = ['expense_type', 'description', 'total_amount']
        
        updated_fields = []
        for key, value in kwargs.items():
            if key in updatable_fields and value:
                setattr(reimbursement, key, value)
                updated_fields.append(key)
        
        if updated_fields:
            reimbursement.updated_at = datetime.now()
            reimbursement.confirmed = False
            db.commit()
            return f"报销单 {reimbursement_no} 已更新：{', '.join(updated_fields)}。请重新确认。\n[[查看报销单详情]]"
        else:
            return f"未找到可更新的字段，请检查参数是否正确"
    except Exception as e:
        db.rollback()
        return f"更新报销单失败：{str(e)}"
    finally:
        db.close()


@tool("确认报销单")
def confirm_reimbursement(reimbursement_no: str) -> str:
    """
    确认报销单，标记为已确认状态
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
            return f"错误：报销单 {reimbursement_no} 当前状态为「{reimbursement.status}」，只有草稿或已驳回状态才能确认"
        
        reimbursement.confirmed = True
        reimbursement.updated_at = datetime.now()
        db.commit()
        
        return f"报销单 {reimbursement_no} 已确认！\n\n确认后您可以提交审批，或继续修改报销单信息。\n[[提交审批]]"
    except Exception as e:
        db.rollback()
        return f"确认报销单失败：{str(e)}"
    finally:
        db.close()


@tool("提交审批")
def submit_for_approval(reimbursement_no: str) -> str:
    """
    将草稿或已驳回的报销单提交至审批流程
    AI智能拆分与建议逻辑：
    - 所有发票合规 + 预算充足：AI建议通过，交由审批人最终决策
    - 部分合规：合规发票合并新建报销单，每张不合规发票单独新建报销单，AI提供建议供审批人参考
    - 全部不合规：每张发票各新建报销单，AI建议驳回
    - 预算不足：全部进入人工审批，AI提示预算情况
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

        if not reimbursement.confirmed:
            return f"错误：报销单 {reimbursement_no} 尚未确认，请先查看报销单详情并确认后再提交审批。\n[[查看报销单详情]]"

        invoices = db.query(Invoice).filter_by(reimbursement_id=reimbursement.id).all()
        vouchers = db.query(Voucher).filter_by(reimbursement_id=reimbursement.id).all()
        
        if not invoices:
            return f"错误：报销单 {reimbursement_no} 未关联任何发票，无法提交审批"

        COMPANY_POLICY = {
            "差旅费": {"daily_limit": 800},
            "招待费": {"per_person_limit": 300},
            "办公用品": {"single_limit": 5000},
            "交通费": {"daily_limit": 200},
            "通讯费": {"monthly_limit": 500},
            "业务招待费": {"per_person_limit": 300}
        }
        
        for inv in invoices:
            invalid_reason = None

            if not inv.invoice_date:
                invalid_reason = "缺少开票日期，无法进行时效性校验"
            else:
                try:
                    invoice_dt = datetime.strptime(inv.invoice_date, "%Y-%m-%d")
                    days_diff = (datetime.now() - invoice_dt).days
                    if days_diff > 90:
                        invalid_reason = f"超过90天有效期（发票日期：{inv.invoice_date}）"
                except ValueError:
                    try:
                        invoice_dt = datetime.strptime(inv.invoice_date, "%Y年%m月%d日")
                        days_diff = (datetime.now() - invoice_dt).days
                        if days_diff > 90:
                            invalid_reason = f"超过90天有效期（发票日期：{inv.invoice_date}）"
                    except ValueError:
                        invalid_reason = "发票日期格式不正确"

            if not invalid_reason and reimbursement.expense_type in COMPANY_POLICY:
                policy = COMPANY_POLICY[reimbursement.expense_type]
                limit_key = list(policy.keys())[0]
                limit_value = policy[limit_key]
                if inv.amount > limit_value:
                    invalid_reason = "金额超过合规标准"

            if invalid_reason:
                inv.is_valid = False
                inv.invalid_reason = invalid_reason
            else:
                inv.is_valid = True
                inv.invalid_reason = None
        db.flush()

        valid_invoices = [inv for inv in invoices if inv.is_valid]
        invalid_invoices = [inv for inv in invoices if not inv.is_valid]
        
        valid_total = sum(inv.amount for inv in valid_invoices)
        voucher_amount = sum(v.amount or 0 for v in vouchers)
        total_with_vouchers = valid_total + voucher_amount
        
        budget_sufficient, budget_message = _check_budget_internal(db, reimbursement.department_id, total_with_vouchers)
        
        created_reimbursements = []
        pending_approval_nos = []
        
        if valid_invoices and budget_sufficient:
            if total_with_vouchers <= 1000 and not invalid_invoices:
                ai_suggestion = _build_ai_suggestion(db, reimbursement, valid_invoices, invalid_invoices, budget_sufficient, budget_message)
                reimbursement.status = "pending"
                reimbursement.ai_suggestion = ai_suggestion
                reimbursement.updated_at = datetime.now()
                
                error = _create_approval_records(db, reimbursement)
                if error:
                    db.rollback()
                    return error
                
                db.commit()
                
                try:
                    from src.tools.email_tool import notify_approver
                    notify_approver.func(reimbursement_no=reimbursement.reimbursement_no)
                except Exception as e:
                    print(f"[通知审批人失败] {reimbursement.reimbursement_no}: {e}")
                
                pending_approval_nos.append(reimbursement.reimbursement_no)
                created_reimbursements.append({
                    "no": reimbursement.reimbursement_no,
                    "amount": total_with_vouchers,
                    "status": "待人工审批",
                    "type": "原报销单",
                    "ai_suggestion": ai_suggestion
                })
            elif total_with_vouchers <= 1000 and invalid_invoices:
                reimbursement.status = "split"
                reimbursement.updated_at = datetime.now()
                
                compliant_no = _get_next_reimbursement_no(db)
                compliant_expense_type = _determine_expense_type(valid_invoices)
                compliant_invoice_details = _build_invoice_details(valid_invoices)
                
                compliant_reimb = Reimbursements(
                    reimbursement_no=compliant_no,
                    source_reimbursement_no=reimbursement_no,
                    employee_id=reimbursement.employee_id,
                    employee_name=reimbursement.employee_name,
                    department_id=reimbursement.department_id,
                    expense_type=compliant_expense_type,
                    total_amount=total_with_vouchers,
                    description=f"合规发票拆分（原单{reimbursement_no}）",
                    status="pending",
                    need_special_approval=False,
                    invoice_details=compliant_invoice_details,
                    ai_suggestion=_build_ai_suggestion(db, None, valid_invoices, [], budget_sufficient, budget_message),
                    applicant_email=reimbursement.applicant_email,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                db.add(compliant_reimb)
                db.flush()
                
                for inv in valid_invoices:
                    inv.reimbursement_id = compliant_reimb.id
                    inv.reimbursement_no = compliant_no
                
                for v in vouchers:
                    v.reimbursement_id = compliant_reimb.id
                    v.reimbursement_no = compliant_no
                
                error = _create_approval_records(db, compliant_reimb)
                if error:
                    db.rollback()
                    return error
                
                pending_approval_nos.append(compliant_no)
                created_reimbursements.append({
                    "no": compliant_no,
                    "amount": total_with_vouchers,
                    "status": "待人工审批",
                    "type": "合规发票合并",
                    "ai_suggestion": compliant_reimb.ai_suggestion
                })
                
                for inv in invalid_invoices:
                    inv_no = _get_next_reimbursement_no(db)
                    inv_invoice_details = _build_invoice_details([inv])
                    
                    invalid_reimb = Reimbursements(
                        reimbursement_no=inv_no,
                        source_reimbursement_no=reimbursement_no,
                        employee_id=reimbursement.employee_id,
                        employee_name=reimbursement.employee_name,
                        department_id=reimbursement.department_id,
                        expense_type=inv.invoice_type_name or "其他",
                        total_amount=inv.amount,
                        description=f"不合规发票拆分（原单{reimbursement_no}），不合规原因：{inv.invalid_reason}",
                        status="pending",
                        need_special_approval=True,
                        invoice_details=inv_invoice_details,
                        ai_suggestion=_build_ai_suggestion(db, None, [], [inv], budget_sufficient, budget_message),
                        applicant_email=reimbursement.applicant_email,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    db.add(invalid_reimb)
                    db.flush()
                    
                    inv.reimbursement_id = invalid_reimb.id
                    inv.reimbursement_no = inv_no
                    
                    error = _create_approval_records(db, invalid_reimb)
                    if error:
                        db.rollback()
                        return error
                    
                    pending_approval_nos.append(inv_no)
                    created_reimbursements.append({
                        "no": inv_no,
                        "amount": inv.amount,
                        "status": "待人工审批",
                        "type": f"不合规发票（{inv.invalid_reason}）",
                        "ai_suggestion": invalid_reimb.ai_suggestion
                    })
                
                db.commit()
                
                for pending_no in pending_approval_nos:
                    try:
                        from src.tools.email_tool import notify_approver
                        notify_approver.func(reimbursement_no=pending_no)
                    except Exception as e:
                        print(f"[通知审批人失败] {pending_no}: {e}")
            else:
                ai_suggestion = _build_ai_suggestion(db, reimbursement, valid_invoices, invalid_invoices, budget_sufficient, budget_message)
                reimbursement.status = "pending"
                reimbursement.ai_suggestion = ai_suggestion
                reimbursement.updated_at = datetime.now()
                
                error = _create_approval_records(db, reimbursement)
                if error:
                    db.rollback()
                    return error
                
                db.commit()
                
                try:
                    from src.tools.email_tool import notify_approver
                    notify_approver.func(reimbursement_no=reimbursement.reimbursement_no)
                except Exception as e:
                    print(f"[通知审批人失败] {reimbursement.reimbursement_no}: {e}")
                
                pending_approval_nos.append(reimbursement.reimbursement_no)
                created_reimbursements.append({
                    "no": reimbursement.reimbursement_no,
                    "amount": total_with_vouchers,
                    "status": "待人工审批",
                    "type": "原报销单（金额>1000元）",
                    "ai_suggestion": ai_suggestion
                })
        elif valid_invoices and not budget_sufficient:
            ai_suggestion = _build_ai_suggestion(db, reimbursement, valid_invoices, invalid_invoices, budget_sufficient, budget_message)
            reimbursement.status = "pending"
            reimbursement.ai_suggestion = ai_suggestion
            reimbursement.updated_at = datetime.now()
            
            error = _create_approval_records(db, reimbursement)
            if error:
                db.rollback()
                return error
            
            db.commit()
            
            try:
                from src.tools.email_tool import notify_approver
                notify_approver.func(reimbursement_no=reimbursement.reimbursement_no)
            except Exception as e:
                print(f"[通知审批人失败] {reimbursement.reimbursement_no}: {e}")
            
            pending_approval_nos.append(reimbursement.reimbursement_no)
            created_reimbursements.append({
                "no": reimbursement.reimbursement_no,
                "amount": total_with_vouchers,
                "status": "待人工审批",
                "type": f"原报销单（{budget_message}）",
                "ai_suggestion": ai_suggestion
            })
        else:
            reimbursement.status = "split"
            reimbursement.updated_at = datetime.now()
            
            for inv in invalid_invoices:
                inv_no = _get_next_reimbursement_no(db)
                inv_invoice_details = _build_invoice_details([inv])
                
                invalid_reimb = Reimbursements(
                    reimbursement_no=inv_no,
                    source_reimbursement_no=reimbursement_no,
                    employee_id=reimbursement.employee_id,
                    employee_name=reimbursement.employee_name,
                    department_id=reimbursement.department_id,
                    expense_type=inv.invoice_type_name or "其他",
                    total_amount=inv.amount,
                    description=f"不合规发票拆分（原单{reimbursement_no}），不合规原因：{inv.invalid_reason}",
                    status="pending",
                    need_special_approval=True,
                    invoice_details=inv_invoice_details,
                    ai_suggestion=_build_ai_suggestion(db, None, [], [inv], budget_sufficient, budget_message),
                    applicant_email=reimbursement.applicant_email,
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                db.add(invalid_reimb)
                db.flush()
                
                inv.reimbursement_id = invalid_reimb.id
                inv.reimbursement_no = inv_no
                
                error = _create_approval_records(db, invalid_reimb)
                if error:
                    db.rollback()
                    return error
                
                pending_approval_nos.append(inv_no)
                created_reimbursements.append({
                    "no": inv_no,
                    "amount": inv.amount,
                    "status": "待人工审批",
                    "type": f"不合规发票（{inv.invalid_reason}）",
                    "ai_suggestion": invalid_reimb.ai_suggestion
                })
            
            db.commit()
            
            for pending_no in pending_approval_nos:
                try:
                    from src.tools.email_tool import notify_approver
                    notify_approver.func(reimbursement_no=pending_no)
                except Exception as e:
                    print(f"[通知审批人失败] {pending_no}: {e}")
        
        result = f"报销单 {reimbursement_no} 提交处理完成！\n\n"
        
        if pending_approval_nos:
            result += f"📋 待人工审批（{len(pending_approval_nos)} 张）：\n"
            for item in created_reimbursements:
                if item["status"] == "待人工审批":
                    result += f"  - {item['no']}：{item['amount']:,.2f}元（{item['type']}）\n"
                    if item.get("ai_suggestion"):
                        result += f"    AI建议：{item['ai_suggestion'].split('】')[0]}】\n"
            result += "\n"
        
        if reimbursement.status == "split":
            result += f"原报销单 {reimbursement_no} 已标记为「已拆分」，可追溯拆分来源。\n"
        
        result += "\n[[进度查询]] [[模拟审批]]"
        
        return result
    except Exception as e:
        db.rollback()
        return f"提交审批失败：{str(e)}"
    finally:
        db.close()
