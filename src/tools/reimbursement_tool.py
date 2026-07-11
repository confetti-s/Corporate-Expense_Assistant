from langchain.tools import tool
from src.db.database import SessionLocal
from src.db.models import Reimbursements, DepartmentApprover, ApprovalRecords, User, Invoice, Voucher, DepartmentBudget
from src.tools.compliance_tool import compliance_check, _check_expense_amount, _determine_sub_expense_type, _check_timeliness, _determine_voucher_sub_expense_type, _VoucherAsInvoice

from datetime import datetime
from sqlalchemy import func
import json


@tool("创建报销单（拆分）")
def create_reimbursement_split(
    employee_id: str,
    employee_name: str,
    department_id: str,
    expense_type: str,
    invoice_ids: str,
    description: str,
    invoice_details_json: str = "[]",
    applicant_email: str = "",
    voucher_ids: str = "",
    voucher_descriptions: str = ""
) -> str:
    """
    按合规性分别创建报销单：合规发票合并一张，不合规发票各一张
    :param employee_id: 员工ID，如 E001
    :param employee_name: 员工姓名
    :param department_id: 部门ID，如 D001-D005
    :param expense_type: 费用类型，如 差旅费、招待费、办公用品、交通费、通讯费
    :param invoice_ids: 发票记录ID列表，用逗号分隔（如"1,2,3"，与voucher_ids至少填一个）
    :param description: 报销说明（必填，简要说明报销事由）
    :param invoice_details_json: 发票OCR结果的JSON数组字符串（可选）
    :param applicant_email: 申请人邮箱（可选，用于审批通知）
    :param voucher_ids: 凭证记录ID列表，用逗号分隔（如"1,2"，与invoice_ids至少填一个）
    :param voucher_descriptions: 凭证描述列表，用|分隔，与voucher_ids顺序对应（如"拜访客户，公司→XX|去机场"）
    """
    db = SessionLocal()
    try:
        if not invoice_ids.strip() and not (voucher_ids and voucher_ids.strip()):
            return "错误：发票ID和凭证ID不能同时为空，至少需要关联一张发票或凭证"
        
        id_list = [int(x.strip()) for x in invoice_ids.split(",") if x.strip()] if invoice_ids.strip() else []
        
        for inv_id in id_list:
            inv = db.query(Invoice).filter_by(id=inv_id).first()
            if inv and inv.reimbursement_id is not None:
                return f"错误：发票记录ID {inv_id}（{inv.invoice_type_name}，{inv.amount:,.2f}元）已关联报销单 {inv.reimbursement_no}，不可重复报销"
        
        valid_invoices = []
        invalid_invoices = []
        for inv_id in id_list:
            inv = db.query(Invoice).filter_by(id=inv_id).first()
            if inv:
                if inv.is_valid:
                    valid_invoices.append(inv)
                else:
                    invalid_invoices.append(inv)
        
        voucher_list = []
        voucher_amount = 0.0
        v_desc_list = [d.strip() for d in voucher_descriptions.split("|") if d.strip()] if voucher_descriptions and voucher_descriptions.strip() else []
        if voucher_ids and voucher_ids.strip():
            vid_list = [int(x.strip()) for x in voucher_ids.split(",") if x.strip()]
            for idx, vid in enumerate(vid_list):
                v = db.query(Voucher).filter_by(id=vid).first()
                if v:
                    if v.reimbursement_id is not None:
                        return f"错误：凭证记录ID {vid}已关联报销单 {v.reimbursement_no}，不可重复报销"
                    # 写入凭证描述
                    if idx < len(v_desc_list) and v_desc_list[idx]:
                        v.description = v_desc_list[idx]
                    voucher_list.append(v)
                    voucher_amount += v.amount or 0
        
        user = db.query(User).filter_by(user_id=employee_id).first()
        if user and user.email:
            applicant_email = user.email
        else:
            applicant_email = None
        
        # 对凭证进行合规检查
        user_role = user.role if user else "employee"
        for v in voucher_list:
            if not v.sub_expense_type:
                v.sub_expense_type = _determine_voucher_sub_expense_type(v) or None
            v_invalid_reasons = []
            timeliness_reason = _check_timeliness(v.payment_date)
            if timeliness_reason:
                v_invalid_reasons.append(timeliness_reason)
            adapter = _VoucherAsInvoice(v)
            amount_reason = _check_expense_amount(expense_type, adapter, user_role, employee_id, db)
            if amount_reason:
                v_invalid_reasons.append(amount_reason)
            v_invalid_reason = "；".join(v_invalid_reasons) if v_invalid_reasons else None
            if v_invalid_reason:
                v.is_valid = False
                v.invalid_reason = v_invalid_reason
            else:
                v.is_valid = True
                v.invalid_reason = None
        db.commit()
        
        created_reimbursements = []
        
        if valid_invoices or voucher_list:
            valid_total = sum(inv.amount for inv in valid_invoices) + voucher_amount
            valid_no = _get_next_reimbursement_no(db)
            need_special_approval = valid_total >= 10000
            
            valid_reimb = Reimbursements(
                reimbursement_no=valid_no,
                employee_id=employee_id,
                employee_name=employee_name,
                department_id=department_id,
                expense_type=expense_type,
                total_amount=valid_total,
                description=f"合规票据合并：{description}" if description else "合规票据合并",
                status="draft",
                need_special_approval=need_special_approval,
                invoice_details=invoice_details_json,
                applicant_email=applicant_email or None,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.add(valid_reimb)
            db.flush()
            
            for inv in valid_invoices:
                inv.reimbursement_id = valid_reimb.id
                inv.reimbursement_no = valid_no
            
            for v in voucher_list:
                v.reimbursement_id = valid_reimb.id
                v.reimbursement_no = valid_no
            
            db.commit()
            
            created_reimbursements.append({
                "no": valid_no,
                "amount": valid_total,
                "type": "合规票据合并",
                "invoice_count": len(valid_invoices),
                "voucher_count": len(voucher_list),
                "status": "草稿"
            })
        
        for inv in invalid_invoices:
            inv_no = _get_next_reimbursement_no(db)
            
            invalid_reimb = Reimbursements(
                reimbursement_no=inv_no,
                employee_id=employee_id,
                employee_name=employee_name,
                department_id=department_id,
                expense_type=expense_type or "其他",
                total_amount=inv.amount,
                description=f"不合规发票（{inv.invalid_reason}）：{description}" if description else f"不合规发票（{inv.invalid_reason}）",
                status="draft",
                need_special_approval=True,
                invoice_details=json.dumps([{"invoice_id": inv.id, "amount": inv.amount, "date": inv.invoice_date, "invalid_reason": inv.invalid_reason}]),
                applicant_email=applicant_email or None,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            db.add(invalid_reimb)
            db.flush()
            
            inv.reimbursement_id = invalid_reimb.id
            inv.reimbursement_no = inv_no
            
            db.commit()
            
            created_reimbursements.append({
                "no": inv_no,
                "amount": inv.amount,
                "type": f"不合规发票（{inv.invalid_reason}）",
                "invoice_count": 1,
                "status": "草稿"
            })
        
        result = f"报销单创建完成！共创建 {len(created_reimbursements)} 张报销单：\n\n"
        for idx, reimb in enumerate(created_reimbursements, 1):
            result += f"{idx}. 报销单号：{reimb['no']}\n"
            result += f"   类型：{reimb['type']}\n"
            result += f"   金额：{reimb['amount']:,.2f} 元\n"
            result += f"   关联发票：{reimb['invoice_count']} 张\n"
            if reimb.get('voucher_count'):
                result += f"   关联凭证：{reimb['voucher_count']} 张\n"
            result += f"   状态：{reimb['status']}\n\n"
        
        result += "接下来我将为您展示每张报销单的详情，请确认是否需要修改。"
        
        return result
    except Exception as e:
        db.rollback()
        return f"创建报销单失败：{str(e)}"
    finally:
        db.close()


@tool("创建报销单")
def create_reimbursement(
    employee_id: str,
    employee_name: str,
    department_id: str,
    expense_type: str,
    invoice_ids: str,
    description: str,
    invoice_details_json: str = "[]",
    applicant_email: str = "",
    voucher_ids: str = "",
    voucher_descriptions: str = ""
) -> str:
    """
    创建一条新的报销记录并存入数据库，返回报销单号
    :param employee_id: 员工ID，如 E001
    :param employee_name: 员工姓名
    :param department_id: 部门ID，如 D001-D006
    :param expense_type: 费用类型（大分类），如 差旅费、业务招待费、日常交通费、办公用品、其他费用
    :param invoice_ids: 发票记录ID列表，用逗号分隔（如"1,2,3"，与voucher_ids至少填一个）
    :param description: 报销说明（必填，简要说明报销事由）
    :param invoice_details_json: 发票OCR结果的JSON数组字符串（可选）
    :param applicant_email: 申请人邮箱（可选，用于审批通知）
    :param voucher_ids: 凭证记录ID列表，用逗号分隔（如"1,2"，与invoice_ids至少填一个）
    :param voucher_descriptions: 凭证描述列表，用|分隔，与voucher_ids顺序对应（如"拜访客户，公司→XX|去机场"）
    """
    db = SessionLocal()
    try:
        if not invoice_ids.strip() and not (voucher_ids and voucher_ids.strip()):
            return "错误：发票ID和凭证ID不能同时为空，至少需要关联一张发票或凭证"
        
        id_list = [int(x.strip()) for x in invoice_ids.split(",") if x.strip()] if invoice_ids.strip() else []
        
        for inv_id in id_list:
            inv = db.query(Invoice).filter_by(id=inv_id).first()
            if inv and inv.reimbursement_id is not None:
                return f"错误：发票记录ID {inv_id}（{inv.invoice_type_name}，{inv.amount:,.2f}元）已关联报销单 {inv.reimbursement_no}，不可重复报销"
        

        # 重新进行合规审查，确保 is_valid 状态是最新的
        user_role = "employee"
        if employee_id:
            user = db.query(User).filter_by(user_id=employee_id).first()
            if user:
                user_role = user.role
        
        for inv_id in id_list:
            inv = db.query(Invoice).filter_by(id=inv_id).first()
            if inv:

                invalid_reasons = []

                # 先推断并写入小分类，合规检查依赖此字段
                if not inv.sub_expense_type:
                    inv.sub_expense_type = _determine_sub_expense_type(inv) or None

                # 1) 90天时效性校验
                timeliness_reason = _check_timeliness(inv.invoice_date)
                if timeliness_reason:
                    invalid_reasons.append(timeliness_reason)

                # 2) 金额合规检查
                amount_reason = _check_expense_amount(expense_type, inv, user_role, employee_id, db)
                if amount_reason:
                    invalid_reasons.append(amount_reason)

                invalid_reason = "；".join(invalid_reasons) if invalid_reasons else None

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
        v_desc_list = [d.strip() for d in voucher_descriptions.split("|") if d.strip()] if voucher_descriptions and voucher_descriptions.strip() else []
        if voucher_ids and voucher_ids.strip():
            vid_list = [int(x.strip()) for x in voucher_ids.split(",") if x.strip()]
            for idx, vid in enumerate(vid_list):
                v = db.query(Voucher).filter_by(id=vid).first()
                if v:
                    if v.reimbursement_id is not None:
                        return f"错误：凭证记录ID {vid}已关联报销单 {v.reimbursement_no}，不可重复报销"
                    # 写入凭证描述
                    if idx < len(v_desc_list) and v_desc_list[idx]:
                        v.description = v_desc_list[idx]
                    voucher_list.append(v)
                    voucher_amount += v.amount or 0
            total_amount += voucher_amount

        # 对凭证进行合规检查
        for v in voucher_list:
            if not v.sub_expense_type:
                v.sub_expense_type = _determine_voucher_sub_expense_type(v) or None
            v_invalid_reasons = []
            timeliness_reason = _check_timeliness(v.payment_date)
            if timeliness_reason:
                v_invalid_reasons.append(timeliness_reason)
            adapter = _VoucherAsInvoice(v)
            amount_reason = _check_expense_amount(expense_type, adapter, user_role, employee_id, db)
            if amount_reason:
                v_invalid_reasons.append(amount_reason)
            v_invalid_reason = "；".join(v_invalid_reasons) if v_invalid_reasons else None
            if v_invalid_reason:
                v.is_valid = False
                v.invalid_reason = v_invalid_reason
            else:
                v.is_valid = True
                v.invalid_reason = None
        db.commit()

        year = datetime.now().strftime("%Y")
        last_record = db.query(Reimbursements).filter(
            Reimbursements.reimbursement_no.like(f"RB{year}%")
        ).order_by(Reimbursements.reimbursement_no.desc()).first()

        next_seq = 1
        if last_record:
            try:
                last_seq = int(last_record.reimbursement_no[-4:])
                next_seq = last_seq + 1
            except (ValueError, IndexError):
                pass

        reimbursement_no = f"RB{year}{str(next_seq).zfill(4)}"
        need_special_approval = total_amount >= 10000

        user = db.query(User).filter_by(user_id=employee_id).first()
        if user and user.email:
            applicant_email = user.email
        else:
            applicant_email = None

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
            # 凭证的小分类默认从报销单大分类推导
            if not v.sub_expense_type:
                category_to_default_sub = {
                    "差旅费": "出差交通",
                    "业务招待费": "餐饮",
                    "日常交通费": "市内公务交通",
                }
                v.sub_expense_type = category_to_default_sub.get(expense_type)
            linked_voucher_count += 1
        db.commit()

        special_note = "（需特殊审批）" if need_special_approval else ""
        invoice_note = f"\n已关联 {linked_count} 张发票记录（合规 {len(valid_invoices)} 张，不合规 {len(invalid_invoices)} 张）" if linked_count > 0 else ""
        valid_voucher_count = sum(1 for v in voucher_list if v.is_valid)
        invalid_voucher_count = sum(1 for v in voucher_list if not v.is_valid)
        voucher_note = f"\n已关联 {linked_voucher_count} 张凭证记录（合规 {valid_voucher_count} 张，不合规 {invalid_voucher_count} 张，金额 {voucher_amount:,.2f} 元）" if linked_voucher_count > 0 else ""
        
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
        
        invalid_vouchers = [v for v in voucher_list if not v.is_valid]
        if invalid_vouchers:
            result += f"不合规凭证明细：\n"
            for v in invalid_vouchers:
                result += f"  - 凭证ID {v.id}：{v.invalid_reason}\n"
        
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
    ).order_by(Reimbursements.reimbursement_no.desc()).first()
    next_seq = 1
    if last_record:
        try:
            last_seq = int(last_record.reimbursement_no[-4:])
            next_seq = last_seq + 1
        except (ValueError, IndexError):
            pass
    return f"RB{year}{str(next_seq).zfill(4)}"


def _check_budget_internal(db, department_id, amount, expense_type=""):
    """检查预算是否充足，按部门+费用类别查询"""
    if expense_type:
        budget = db.query(DepartmentBudget).filter_by(
            department_id=department_id, expense_type=expense_type
        ).first()
        if not budget:
            return False, f"部门 {department_id} 的 {expense_type} 预算信息不存在"

        spent = db.query(func.sum(Reimbursements.total_amount)).filter(
            Reimbursements.department_id == department_id,
            Reimbursements.expense_type == expense_type,
            Reimbursements.status == "approved"
        ).scalar() or 0.0

        remaining = budget.budget_amount - spent
        if remaining >= amount:
            return True, f"【{expense_type}】预算充足，剩余 {remaining:,.2f} 元"
        else:
            return False, f"【{expense_type}】预算不足，剩余 {remaining:,.2f} 元，超出 {amount - remaining:,.2f} 元"
    else:
        # 兼容：无类别时查总预算
        budgets = db.query(DepartmentBudget).filter_by(department_id=department_id).all()
        if not budgets:
            return False, "部门预算信息不存在"

        total_budget = sum(b.budget_amount for b in budgets)
        spent = db.query(func.sum(Reimbursements.total_amount)).filter(
            Reimbursements.department_id == department_id,
            Reimbursements.status == "approved"
        ).scalar() or 0.0

        remaining = total_budget - spent
        if remaining >= amount:
            return True, f"预算充足，剩余 {remaining:,.2f} 元"
        else:
            return False, f"预算不足，剩余 {remaining:,.2f} 元，超出 {amount - remaining:,.2f} 元"


def _create_approval_records(db, reimbursement):
    dept_approvers = db.query(DepartmentApprover).filter_by(
        department_id=reimbursement.department_id
    ).order_by(DepartmentApprover.approval_level).all()
    
    if not dept_approvers:
        return f"错误：部门 {reimbursement.department_id} 未配置审批人"
    
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


def _build_ai_suggestion(db, reimbursement, valid_invoices, invalid_invoices, budget_sufficient, budget_message, valid_vouchers=None, invalid_vouchers=None):
    valid_count = len(valid_invoices)
    invalid_count = len(invalid_invoices)
    valid_voucher_count = len(valid_vouchers) if valid_vouchers else 0
    invalid_voucher_count = len(invalid_vouchers) if invalid_vouchers else 0
    total_valid = valid_count + valid_voucher_count
    total_invalid = invalid_count + invalid_voucher_count
    total_amount = reimbursement.total_amount if reimbursement else sum(inv.amount for inv in valid_invoices) + sum(inv.amount for inv in invalid_invoices)
    
    if total_valid == 0 and total_invalid > 0:
        suggestion = f"【AI建议：驳回】\n理由：\n  - 所有票据均不合规（发票{invalid_count}张，凭证{invalid_voucher_count}张）\n"
        for inv in invalid_invoices:
            suggestion += f"    * 发票ID{inv.id}：{inv.invalid_reason}\n"
        if invalid_vouchers:
            for v in invalid_vouchers:
                suggestion += f"    * 凭证ID{v.id}：{v.invalid_reason}\n"
    elif total_invalid == 0 and budget_sufficient:
        bill_info = f"合规发票{valid_count}张" + (f"，合规凭证{valid_voucher_count}张" if valid_voucher_count > 0 else "")
        if total_amount <= 1000:
            suggestion = f"【AI建议：通过】\n理由：\n  - {bill_info}\n  - 部门预算充足\n  - 金额{total_amount:,.2f}元≤1000元，符合快速审批条件\n"
        else:
            suggestion = f"【AI建议：通过】\n理由：\n  - {bill_info}\n  - 部门预算充足\n  - 金额{total_amount:,.2f}元>1000元，需按金额对应审批级别处理\n"
    elif total_invalid > 0 and budget_sufficient:
        suggestion = f"【AI建议：谨慎审批】\n理由：\n  - 合规发票{valid_count}张，不合规发票{invalid_count}张"
        if valid_voucher_count > 0 or invalid_voucher_count > 0:
            suggestion += f"，合规凭证{valid_voucher_count}张，不合规凭证{invalid_voucher_count}张"
        suggestion += f"\n  - 部门预算充足\n  - 建议仔细审核不合规票据的具体原因\n"
        for inv in invalid_invoices:
            suggestion += f"    * 发票ID{inv.id}：{inv.invalid_reason}\n"
        if invalid_vouchers:
            for v in invalid_vouchers:
                suggestion += f"    * 凭证ID{v.id}：{v.invalid_reason}\n"
    else:
        suggestion = f"【AI建议：谨慎审批】\n理由：\n  - {budget_message}\n  - 合规发票{valid_count}张，不合规发票{invalid_count}张"
        if valid_voucher_count > 0 or invalid_voucher_count > 0:
            suggestion += f"，合规凭证{valid_voucher_count}张，不合规凭证{invalid_voucher_count}张"
        suggestion += "\n"
    
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
        vouchers = db.query(Voucher).filter_by(reimbursement_id=reimbursement.id).all()
        
        result = f"## 📋 报销单详情\n\n"
        result += f"| 项目 | 内容 |\n"
        result += f"|:---|:---|\n"
        result += f"| 报销单号 | {reimbursement.reimbursement_no} |\n"
        result += f"| 申请人 | {reimbursement.employee_name}（{reimbursement.employee_id}） |\n"
        result += f"| 部门 | {reimbursement.department_id} |\n"
        result += f"| 报销类别 | {reimbursement.expense_type} |\n"
        result += f"| 申请总金额 | {reimbursement.total_amount:,.2f} 元 |\n"
        result += f"| 报销说明 | {reimbursement.description or '-'} |\n"
        result += f"| 当前状态 | {reimbursement.status} |\n"
        result += f"| 确认状态 | {'✅ 已确认' if reimbursement.confirmed else '❌ 未确认'} |\n"
        if reimbursement.ai_suggestion:
            result += f"| AI审核建议 | {reimbursement.ai_suggestion} |\n"
        result += f"| 创建时间 | {reimbursement.created_at.strftime('%Y-%m-%d %H:%M')} |\n"
        result += f"| 更新时间 | {reimbursement.updated_at.strftime('%Y-%m-%d %H:%M')} |\n"
        
        # 统一费用明细表：发票和凭证合在一起
        items = []
        for inv in invoices:
            items.append({
                "sub_expense_type": inv.sub_expense_type or "其他",
                "description": inv.description or "-",
                "date": inv.invoice_date or "-",
                "amount": inv.amount,
                "remark": "发票",
                "ai_suggestion": "合规" if inv.is_valid else f"不合规：{inv.invalid_reason}",
            })
        for v in vouchers:
            items.append({
                "sub_expense_type": v.sub_expense_type or "其他",
                "description": v.description or "-",
                "date": v.payment_date or "-",
                "amount": v.amount,
                "remark": "凭证",
                "ai_suggestion": "合规" if v.is_valid else f"不合规：{v.invalid_reason}",
            })
        
        if items:
            result += f"\n### 🧾 费用明细\n\n"
            result += f"| 序号 | 费用项目 | 详细说明 | 消费日期 | 金额（元） | 备注 | AI建议 |\n"
            result += f"|:---|:---|:---|:---|:---|:---|:---|\n"
            for idx, item in enumerate(items, 1):
                ai_status = "✅ " + item["ai_suggestion"] if item["ai_suggestion"] == "合规" else "❌ " + item["ai_suggestion"]
                result += f"| {idx} | {item['sub_expense_type']} | {item['description']} | {item['date']} | {item['amount']:,.2f} | {item['remark']} | {ai_status} |\n"
        
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
    AI提供审核建议但最终由审批人决策
    无论发票是否合规，只要用户确认提交，都会交给上级审批人进行人工检查
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
        
        if not invoices and not vouchers:
            return f"错误：报销单 {reimbursement_no} 未关联任何发票或凭证，无法提交审批"

        valid_invoices = [inv for inv in invoices if inv.is_valid]
        invalid_invoices = [inv for inv in invoices if not inv.is_valid]
        valid_vouchers = [v for v in vouchers if v.is_valid]
        invalid_vouchers = [v for v in vouchers if not v.is_valid]
        
        voucher_amount = sum(v.amount or 0 for v in vouchers)
        total_with_vouchers = reimbursement.total_amount
        
        budget_sufficient, budget_message = _check_budget_internal(db, reimbursement.department_id, total_with_vouchers, reimbursement.expense_type)
        
        ai_suggestion = _build_ai_suggestion(db, reimbursement, valid_invoices, invalid_invoices, budget_sufficient, budget_message, valid_vouchers, invalid_vouchers)
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
        
        result = f"报销单 {reimbursement_no} 提交处理完成！\n\n"
        result += f"📋 待人工审批：\n"
        result += f"  - {reimbursement_no}：{total_with_vouchers:,.2f}元\n"
        result += f"    AI建议：{ai_suggestion}\n\n"
        result += "[[进度查询]] [[模拟审批]]"
        
        return result
    
    except Exception as e:
        db.rollback()
        return f"提交审批失败：{str(e)}"
    finally:
        db.close()
