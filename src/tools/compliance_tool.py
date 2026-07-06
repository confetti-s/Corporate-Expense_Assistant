from langchain.tools import tool

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
def compliance_check(expense_type: str, amount: float, quantity: int = 1) -> str:
    """
    检查费用是否符合公司报销政策
    :param expense_type: 费用类型，如 差旅费、招待费、办公用品、交通费、通讯费
    :param amount: 报销金额
    :param quantity: 数量/人数/天数（默认1）
    :return: 合规审查结果字符串
    """
    if expense_type not in COMPANY_POLICY:
        return f"未知费用类型：{expense_type}，请选择以下类型之一：{', '.join(COMPANY_POLICY.keys())}"
    
    policy = COMPANY_POLICY[expense_type]
    limit_key = list(policy.keys())[0]
    limit_value = policy[limit_key]
    description = policy["description"]
    
    per_unit_amount = amount / quantity
    
    if per_unit_amount <= limit_value:
        return f"""合规审查通过！
费用类型：{expense_type}
报销金额：{amount:,.2f} 元
{description}：{limit_value:,.2f} 元
本次人均/每日金额：{per_unit_amount:,.2f} 元
符合公司报销政策。"""
    else:
        excess = per_unit_amount - limit_value
        return f"""合规审查不通过！
费用类型：{expense_type}
报销金额：{amount:,.2f} 元
{description}：{limit_value:,.2f} 元
本次人均/每日金额：{per_unit_amount:,.2f} 元
超出标准：{excess:,.2f} 元
需要特殊审批说明。"""

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