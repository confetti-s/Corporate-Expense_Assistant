from langchain.tools import tool
from datetime import datetime
from src.db.database import SessionLocal
from src.db.models import Invoice

COMPANY_POLICY = {
    "差旅费": {
        "daily_limit": 800,
        "description": "每人每天差旅费（含交通、住宿、餐饮）上限"
    },
    "招待费": {
        "per_person_limit": 300,
        "description": "每人次招待费用上限"
    },
    "办公用品": {
        "single_limit": 5000,
        "description": "单次办公用品采购上限"
    },
    "交通费": {
        "daily_limit": 200,
        "description": "每人每天交通费用上限"
    },
    "通讯费": {
        "monthly_limit": 500,
        "description": "每人每月通讯费用上限"
    }
}

@tool("合规审查")
def compliance_check(expense_type: str, invoice_ids: str) -> str:
    """
    检查多张发票是否符合公司报销政策（含90天时效性校验和金额合规检查）
    :param expense_type: 费用类型，如 差旅费、招待费、办公用品、交通费、通讯费
    :param invoice_ids: 发票ID列表，用逗号分隔，如 "1,2,3"
    :return: 合规审查结果字符串
    """
    if expense_type not in COMPANY_POLICY:
        return f"未知费用类型：{expense_type}，请选择以下类型之一：{', '.join(COMPANY_POLICY.keys())}"
    
    if not invoice_ids.strip():
        return "错误：发票ID列表不能为空"
    
    db = SessionLocal()
    try:
        id_list = [int(x.strip()) for x in invoice_ids.split(",") if x.strip()]
        
        invalid_invoices = []
        valid_invoices = []
        
        policy = COMPANY_POLICY[expense_type]
        limit_key = list(policy.keys())[0]
        limit_value = policy[limit_key]
        
        for inv_id in id_list:
            invoice = db.query(Invoice).filter_by(id=inv_id).first()
            if not invoice:
                invalid_invoices.append({
                    "id": inv_id,
                    "reason": "发票记录不存在",
                    "date": ""
                })
                continue
            
            invalid_reason = None
            
            if not invoice.invoice_date:
                invalid_reason = "缺少开票日期，无法进行时效性校验"
            else:
                try:
                    invoice_dt = datetime.strptime(invoice.invoice_date, "%Y-%m-%d")
                    days_diff = (datetime.now() - invoice_dt).days
                    
                    if days_diff > 90:
                        invalid_reason = f"超过90天有效期（发票日期：{invoice.invoice_date}）"
                except ValueError:
                    invalid_reason = "发票日期格式不正确"
            
            if not invalid_reason:
                if invoice.amount > limit_value:
                    invalid_reason = "金额超过合规标准"
            
            if invalid_reason:
                invoice.is_valid = False
                invoice.invalid_reason = invalid_reason
                invalid_invoices.append({
                    "id": inv_id,
                    "reason": invalid_reason,
                    "date": invoice.invoice_date
                })
            else:
                invoice.is_valid = True
                invoice.invalid_reason = None
                valid_invoices.append(invoice)
        
        db.commit()
        
        valid_total = sum(inv.amount for inv in valid_invoices)
        
        result = f"合规审查完成。\n"
        result += f"合规发票：{len(valid_invoices)} 张，合计金额 {valid_total:,.2f} 元\n"
        
        if invalid_invoices:
            result += f"不合规发票：{len(invalid_invoices)} 张\n"
            for inv in invalid_invoices:
                result += f"  - 发票 ID {inv['id']}：{inv['reason']}\n"
        
        result += f"本次可报销金额：{valid_total:,.2f} 元"
        
        return result
    
    except ValueError:
        return "错误：发票ID列表格式不正确，请确保为数字，用逗号分隔"
    except Exception as e:
        db.rollback()
        return f"合规审查失败：{str(e)}"
    finally:
        db.close()

@tool("金额汇总")
def calculate_total_amount(amounts: str) -> str:
    """
    汇总多张票据的总金额
    :param amounts: 金额列表，用逗号分隔，如 "100.50, 200.00, 350.75"
    :return: 汇总结果字符串
    """
    try:
        amount_list = [float(a.strip()) for a in amounts.split(',')]
        total = sum(amount_list)
        count = len(amount_list)
        
        return f"""金额汇总结果：
票据数量：{count} 张
明细金额：{', '.join([f'{a:,.2f}' for a in amount_list])} 元
总金额：{total:,.2f} 元"""
    except ValueError:
        return f"无法解析金额列表：{amounts}，请确保输入格式正确，如 '100.50, 200.00'"

@tool("获取报销政策")
def get_expense_policy() -> str:
    """
    获取公司报销政策说明
    :return: 报销政策字符串
    """
    result = "公司报销政策说明：\n\n"
    
    for expense_type, policy in COMPANY_POLICY.items():
        limit_key = list(policy.keys())[0]
        limit_value = policy[limit_key]
        description = policy["description"]
        
        result += f"""{expense_type}：
  {description}：{limit_value:,.2f} 元
------------------------
"""
    
    return result