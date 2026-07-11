from langchain.tools import tool
from datetime import datetime
from src.db.database import SessionLocal
from src.db.models import Invoice, Voucher, User, Reimbursements
from sqlalchemy import func


def _determine_sub_expense_type(invoice):
    """根据发票类型和卖方名称推断费用小分类"""
    type_name = invoice.invoice_type_name or ""
    seller_name = invoice.seller_name or ""

    # 特定发票类型直接映射
    type_to_sub = {
        "火车票": "出差交通",
        "机票": "出差交通",
        "出租车票": "市内公务交通",
        "住宿发票": "住宿",
        "餐饮发票": "餐饮",
    }
    if type_name in type_to_sub:
        return type_to_sub[type_name]

    # 增值税发票等通用类型，根据卖方名称关键词推断
    seller_lower = seller_name.lower()
    if any(kw in seller_lower for kw in ["酒店", "宾馆", "旅馆", "公寓", "民宿", "希尔顿", "如家", "汉庭", "全季", "锦江", "万豪", "洲际", "香格里拉"]):
        return "住宿"
    if any(kw in seller_lower for kw in ["餐饮", "饭店", "餐厅", "酒楼", "食府", "美食", "茶楼", "咖啡", "肯德基", "麦当劳", "星巴克", "火锅", "烧烤"]):
        return "餐饮"
    if any(kw in seller_lower for kw in ["航空", "机票", "铁路", "12306", "出租", "网约车", "滴滴", "神州"]):
        return "出差交通"
    if any(kw in seller_lower for kw in ["办公用品", "文具", "打印", "复印", "办公设备"]):
        return "办公用品"
    if any(kw in seller_lower for kw in ["快递", "物流", "顺丰", "中通", "圆通", "韵达", "申通"]):
        return "快递"
    if any(kw in seller_lower for kw in ["停车", "高速", "路桥"]):
        return "停车费"

    # 无法判断时返回空，由 Agent 在对话中确认
    return ""


def _determine_voucher_sub_expense_type(voucher):
    """根据凭证类型和收款方名称推断费用小分类"""
    if voucher.sub_expense_type:
        return voucher.sub_expense_type

    payee = voucher.payee or ""
    payee_lower = payee.lower()
    if any(kw in payee_lower for kw in ["酒店", "宾馆", "旅馆", "公寓", "民宿", "希尔顿", "如家", "汉庭", "全季", "锦江", "万豪", "洲际", "香格里拉"]):
        return "住宿"
    if any(kw in payee_lower for kw in ["餐饮", "饭店", "餐厅", "酒楼", "食府", "美食", "茶楼", "咖啡", "肯德基", "麦当劳", "星巴克", "火锅", "烧烤"]):
        return "餐饮"
    if any(kw in payee_lower for kw in ["航空", "机票", "铁路", "12306", "出租", "网约车", "滴滴", "神州", "花小猪", "高德", "打车", "曹操", "T3出行", "美团打车", "哈啰"]):
        return "出差交通"
    if any(kw in payee_lower for kw in ["办公用品", "文具", "打印", "复印", "办公设备"]):
        return "办公用品"
    if any(kw in payee_lower for kw in ["快递", "物流", "顺丰", "中通", "圆通", "韵达", "申通"]):
        return "快递"
    if any(kw in payee_lower for kw in ["停车", "高速", "路桥"]):
        return "停车费"

    return ""


def _check_timeliness(date_str: str):
    """通用90天时效性校验，合规返回None，不合规返回原因字符串"""
    if not date_str:
        return "缺少日期，无法进行时效性校验"
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        days_diff = (datetime.now() - dt).days
        if days_diff > 90:
            return f"超过90天有效期（日期：{date_str}）"
    except ValueError:
        try:
            dt = datetime.strptime(date_str, "%Y年%m月%d日")
            days_diff = (datetime.now() - dt).days
            if days_diff > 90:
                return f"超过90天有效期（日期：{date_str}）"
        except ValueError:
            return "日期格式不正确"
    return None


class _VoucherAsInvoice:
    """将 Voucher 适配为类 Invoice 接口，以复用 _check_expense_amount 等检查逻辑"""
    def __init__(self, voucher):
        self.amount = voucher.amount
        self.invoice_date = voucher.payment_date
        self.seller_name = voucher.payee
        self.invoice_type_name = voucher.voucher_type
        self.description = voucher.description
        self.sub_expense_type = voucher.sub_expense_type


# ==================== 城市等级映射 ====================
CITY_TIERS = {
    # 一线城市
    "北京": 1, "上海": 1, "广州": 1, "深圳": 1, "杭州": 1,
    # 二线省会城市
    "成都": 2, "武汉": 2, "南京": 2, "重庆": 2, "西安": 2, "长沙": 2,
    "郑州": 2, "济南": 2, "合肥": 2, "昆明": 2, "福州": 2, "南昌": 2,
    "贵阳": 2, "太原": 2, "石家庄": 2, "兰州": 2, "南宁": 2, "乌鲁木齐": 2,
    "哈尔滨": 2, "沈阳": 2, "长春": 2, "呼和浩特": 2, "海口": 2, "银川": 2,
    "西宁": 2, "拉萨": 2, "天津": 2, "苏州": 2, "厦门": 2, "青岛": 2,
    "大连": 2, "宁波": 2,
}

# ==================== 差旅交通标准（按职级） ====================
TRAVEL_TRANSPORT_LIMITS = {
    "employee": {
        "高铁/动车": "二等座",
        "飞机": 1000,  # 经济舱单程上限
        "市内交通": 50,  # 每日上限
        "长途汽车": None,  # 实报实销
    },
    "manager": {
        "高铁/动车": "商务座",
        "飞机": None,  # 商务舱，无上限
        "市内交通": None,  # 实报实销无上限
        "长途汽车": None,
    },
    "director": {
        "高铁/动车": "商务座/特等座",
        "飞机": None,  # 头等舱，无上限
        "市内交通": None,
        "长途汽车": None,
    },
    "general_manager": {
        "高铁/动车": "商务座/特等座/专车",
        "飞机": None,
        "市内交通": None,
        "长途汽车": None,
    },
}

# ==================== 住宿标准（城市等级 × 职级，元/晚） ====================
HOTEL_LIMITS = {
    1: {"employee": 350, "manager": 500, "director": 650, "general_manager": None},
    2: {"employee": 280, "manager": 400, "director": 520, "general_manager": None},
    3: {"employee": 220, "manager": 320, "director": 420, "general_manager": None},
}

# ==================== 餐补标准（按职级，元/天） ====================
MEAL_ALLOWANCE = {
    "employee": 80,
    "manager": 180,
    "director": 180,
    "general_manager": 180,
}

# ==================== 日常交通费月度上限 ====================
DAILY_TRANSPORT_MONTHLY_LIMIT = 300

# ==================== 业务招待费标准 ====================
ENTERTAINMENT_LIMITS = {
    "single_person_per_capita": 100,  # 单人接待人均
    "multi_person_per_capita": 150,    # 多人聚餐人均
    "single_total_threshold": 1000,    # 单次超此金额需总监提前审批
    "gift_single_limit": 300,          # 礼品单份上限
    "gift_monthly_per_client": 1000,   # 月度同客户礼品累计上限
}

# ==================== 有效费用类型 ====================
VALID_EXPENSE_TYPES = ["差旅费", "业务招待费", "日常交通费", "办公用品", "其他费用"]

# 有效费用小分类映射
SUB_EXPENSE_TYPES = {
    "差旅费": ["出差交通", "住宿", "餐补"],
    "业务招待费": ["餐饮", "礼品"],
    "日常交通费": ["市内公务交通", "停车费", "高速费"],
    "办公用品": [],
    "其他费用": ["快递", "打印"],
}


def _get_city_tier(city_name):
    """根据城市名获取城市等级，默认3（三四线）"""
    if not city_name:
        return 3
    return CITY_TIERS.get(city_name, 3)


def _get_user_role(employee_id):
    """根据员工ID获取用户职级"""
    db = SessionLocal()
    try:
        user = db.query(User).filter_by(user_id=employee_id).first()
        if user:
            return user.role
        return "employee"
    finally:
        db.close()


@tool("合规审查")
def compliance_check(expense_type: str, invoice_ids: str, employee_id: str = "") -> str:
    """
    检查多张发票是否符合公司报销政策（含90天时效性校验和金额合规检查）
    :param expense_type: 费用类型（大分类），如 差旅费、业务招待费、日常交通费、办公用品、其他费用
    :param invoice_ids: 发票ID列表，用逗号分隔，如 "1,2,3"
    :param employee_id: 申请人员工ID，如 E001（用于判断职级和部门，影响合规标准）
    :return: 合规审查结果字符串
    """
    if expense_type not in VALID_EXPENSE_TYPES:
        return f"未知费用类型：{expense_type}，请选择以下类型之一：{', '.join(VALID_EXPENSE_TYPES)}"

    if not invoice_ids.strip():
        return "错误：发票ID列表不能为空"

    user_role = _get_user_role(employee_id) if employee_id else "employee"

    # 办公用品特殊校验：仅行政部员工可报销
    if expense_type == "办公用品":
        db_check = SessionLocal()
        try:
            user = db_check.query(User).filter_by(user_id=employee_id).first()
            if user and user.department_id != "D006":
                return (
                    f"合规审查结果：不予通过\n"
                    f"原因：办公用品仅限行政部员工集中采购报销，"
                    f"您所在部门为 {user.department_id}，无权报销办公用品。"
                )
        finally:
            db_check.close()

    db = SessionLocal()
    try:
        id_list = [int(x.strip()) for x in invoice_ids.split(",") if x.strip()]

        invalid_invoices = []
        valid_invoices = []

        for inv_id in id_list:
            invoice = db.query(Invoice).filter_by(id=inv_id).first()
            if not invoice:
                invalid_invoices.append({
                    "id": inv_id,
                    "reason": "发票记录不存在",
                    "date": ""
                })
                continue

            # 自动推断小分类（合规检查依赖此字段）
            if not invoice.sub_expense_type:
                invoice.sub_expense_type = _determine_sub_expense_type(invoice) or None

            invalid_reasons = []

            # 1) 90天时效性校验
            timeliness_reason = _check_timeliness(invoice.invoice_date)
            if timeliness_reason:
                invalid_reasons.append(timeliness_reason)

            # 2) 按费用类型进行金额合规检查
            amount_reason = _check_expense_amount(expense_type, invoice, user_role, employee_id, db)
            if amount_reason:
                invalid_reasons.append(amount_reason)

            invalid_reason = "；".join(invalid_reasons) if invalid_reasons else None

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
        result += f"费用类型：{expense_type} | 申请人职级：{_role_display(user_role)}\n"
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


def _check_expense_amount(expense_type, invoice, user_role, employee_id, db):
    """按费用类型检查金额合规性"""
    sub_type = invoice.sub_expense_type or ""

    if expense_type == "差旅费":
        return _check_travel_expense(invoice, sub_type, user_role, db)
    elif expense_type == "业务招待费":
        return _check_entertainment_expense(invoice, sub_type, user_role, db)
    elif expense_type == "日常交通费":
        return _check_daily_transport_expense(invoice, sub_type, user_role, employee_id, db)
    elif expense_type == "办公用品":
        return None  # 已在上面做过行政部校验，金额无上限
    elif expense_type == "其他费用":
        return None  # 实报实销

    return None


def _check_travel_expense(invoice, sub_type, user_role, db):
    """差旅费合规检查"""
    if sub_type == "出差交通":
        desc = invoice.description or ""
        type_name = invoice.invoice_type_name or ""

        # 火车票：检查座位等级
        if "火车" in type_name or "高铁" in type_name or "动车" in type_name:
            if user_role == "employee":
                # 基层员工只能二等座
                if "商务座" in desc or "特等座" in desc or "一等座" in desc:
                    return f"基层员工高铁/动车仅限二等座，实际乘坐{desc}"
                # 描述为空时，要求补充座位信息
                if not desc or "座" not in desc:
                    return f"火车票缺少座位信息，无法判断是否合规（基层员工仅限二等座）。请先调用update_invoice_description补充座位类型"
            # manager及以上可坐商务座，无限制

        # 机票：检查舱位和金额
        elif "飞机" in type_name or "机票" in type_name:
            if user_role == "employee":
                if "商务舱" in desc or "头等舱" in desc:
                    return f"基层员工飞机仅限经济舱，实际乘坐{desc}"
                if invoice.amount > 1000:
                    return f"基层员工飞机经济舱单程上限1000元，实际 {invoice.amount:,.2f} 元"
                # 描述为空时，要求补充舱位信息
                if not desc or "舱" not in desc:
                    return f"机票缺少舱位信息，无法判断是否合规（基层员工仅限经济舱≤1000元）。请先调用update_invoice_description补充舱位信息"
            elif user_role == "manager":
                if "头等舱" in desc:
                    return f"部门经理飞机仅限商务舱，实际乘坐头等舱"

        # 出租车/网约车：市内交通每日50元上限（仅基层员工）
        elif "出租" in type_name or "网约车" in type_name:
            if user_role == "employee" and invoice.amount > 50:
                return f"基层员工出差市内交通每日上限50元，实际 {invoice.amount:,.2f} 元"

        return None

    elif sub_type == "住宿":
        city = _extract_city_from_name(invoice.seller_name or "")
        tier = _get_city_tier(city)
        limit = HOTEL_LIMITS.get(tier, HOTEL_LIMITS[3]).get(user_role)
        tier_name = {1: "一线", 2: "二线", 3: "三四线"}.get(tier, "三四线")
        if limit is None:
            return None  # 总经理无上限
        # 尝试从 description 中提取入住/退房日期来计算天数
        nights = _extract_nights_from_description(invoice.description or "")
        if nights and nights > 0:
            per_night = invoice.amount / nights
            if per_night > limit:
                return f"{tier_name}城市住宿标准 {_role_display(user_role)} {limit}元/晚，实际 {per_night:,.2f}元/晚（{invoice.amount:,.2f}元/{nights}晚）"
            return None
        else:
            # 无描述信息，无法判断每晚单价，默认标记为需补充信息
            return f"住宿发票缺少描述信息，无法判断每晚单价是否超标（{tier_name}城市{_role_display(user_role)}标准：{limit}元/晚）。请先调用update_invoice_description补充入住/退房日期和房型，再重新进行合规审查"

    elif sub_type == "餐补":
        # 餐补无需发票，按天数计算，此处仅做职级标准校验
        allowance = MEAL_ALLOWANCE.get(user_role, 80)
        if invoice.amount > allowance:
            return f"餐补标准 {_role_display(user_role)} {allowance}元/天，实际 {invoice.amount:,.2f} 元"
        return None

    return None


def _check_entertainment_expense(invoice, sub_type, user_role, db):
    """业务招待费合规检查"""
    if sub_type == "餐饮":
        # 简化判断：单张发票金额超过1000元需总监提前审批（标记提示，不直接判不合规）
        if invoice.amount > ENTERTAINMENT_LIMITS["single_total_threshold"]:
            # 不直接判不合规，只提示需总监审批
            return None
        # 从描述中提取用餐人数，判断人均标准
        desc = invoice.description or ""
        import re
        match = re.search(r'(\d+)\s*人', desc)
        if match:
            person_count = int(match.group(1))
            if person_count > 0:
                per_capita = invoice.amount / person_count
                if person_count == 1:
                    limit = ENTERTAINMENT_LIMITS["single_person_per_capita"]
                    if per_capita > limit:
                        return f"单人招待人均上限 {limit}元，实际人均 {per_capita:,.2f}元（{invoice.amount:,.2f}元/1人）"
                else:
                    limit = ENTERTAINMENT_LIMITS["multi_person_per_capita"]
                    if per_capita > limit:
                        return f"多人聚餐人均上限 {limit}元，实际人均 {per_capita:,.2f}元（{invoice.amount:,.2f}元/{person_count}人）"
        # 描述中未提取到人数，跳过人均检查
        return None

    elif sub_type == "礼品":
        if invoice.amount > ENTERTAINMENT_LIMITS["gift_single_limit"]:
            return f"单份礼品上限 {ENTERTAINMENT_LIMITS['gift_single_limit']}元，实际 {invoice.amount:,.2f} 元"
        # 月度同客户累计暂不做自动检查（需要更复杂的逻辑）
        return None

    return None


def _extract_nights_from_description(description):
    """从发票描述中提取住宿天数，格式如 '入住2026-06-01至2026-06-09，标准单人间'"""
    import re
    # 匹配 "入住YYYY-MM-DD至YYYY-MM-DD" 或 "入住YYYY/MM/DD至YYYY/MM/DD"
    match = re.search(r'入住\s*(\d{4}[-/]\d{2}[-/]\d{2})\s*至\s*(\d{4}[-/]\d{2}[-/]\d{2})', description)
    if match:
        try:
            from datetime import datetime as dt
            fmt = "%Y-%m-%d" if "-" in match.group(1) else "%Y/%m/%d"
            start = dt.strptime(match.group(1), fmt)
            end = dt.strptime(match.group(2), fmt)
            nights = (end - start).days
            return nights if nights > 0 else None
        except ValueError:
            pass
    # 匹配 "X晚" 或 "X天"
    match = re.search(r'(\d+)\s*[晚天]', description)
    if match:
        return int(match.group(1))
    return None


def _check_daily_transport_expense(invoice, sub_type, user_role, employee_id, db):
    """日常交通费合规检查"""
    # 月度上限300元
    if employee_id:
        current_month = datetime.now().strftime("%Y-%m")
        month_start = datetime.now().replace(day=1)
        # 查询本月已通过的日常交通费报销总额
        month_total = db.query(func.sum(Reimbursements.total_amount)).filter(
            Reimbursements.employee_id == employee_id,
            Reimbursements.expense_type == "日常交通费",
            Reimbursements.status.in_(["approved", "pending", "reviewing"]),
            Reimbursements.created_at >= month_start
        ).scalar() or 0.0

        if month_total + invoice.amount > DAILY_TRANSPORT_MONTHLY_LIMIT:
            return f"日常交通费月度上限 {DAILY_TRANSPORT_MONTHLY_LIMIT}元，本月已报 {month_total:,.2f}元，本次 {invoice.amount:,.2f}元 后将超标"

    return None


def _extract_city_from_name(name):
    """从酒店/商户名称中提取城市名"""
    for city in CITY_TIERS:
        if city in name:
            return city
    return None


@tool("凭证合规审查")
def voucher_compliance_check(expense_type: str, voucher_ids: str, employee_id: str = "") -> str:
    """
    检查多张凭证是否符合公司报销政策（含90天时效性校验和金额合规检查）
    :param expense_type: 费用类型（大分类），如 差旅费、业务招待费、日常交通费、办公用品、其他费用
    :param voucher_ids: 凭证ID列表，用逗号分隔，如 "1,2,3"
    :param employee_id: 申请人员工ID，如 E001（用于判断职级和部门，影响合规标准）
    :return: 合规审查结果字符串
    """
    if expense_type not in VALID_EXPENSE_TYPES:
        return f"未知费用类型：{expense_type}，请选择以下类型之一：{', '.join(VALID_EXPENSE_TYPES)}"

    if not voucher_ids.strip():
        return "错误：凭证ID列表不能为空"

    user_role = _get_user_role(employee_id) if employee_id else "employee"

    # 办公用品特殊校验：仅行政部员工可报销
    if expense_type == "办公用品":
        db_check = SessionLocal()
        try:
            user = db_check.query(User).filter_by(user_id=employee_id).first()
            if user and user.department_id != "D006":
                return (
                    f"合规审查结果：不予通过\n"
                    f"原因：办公用品仅限行政部员工集中采购报销，"
                    f"您所在部门为 {user.department_id}，无权报销办公用品。"
                )
        finally:
            db_check.close()

    db = SessionLocal()
    try:
        id_list = [int(x.strip()) for x in voucher_ids.split(",") if x.strip()]

        invalid_vouchers = []
        valid_vouchers = []

        for vid in id_list:
            voucher = db.query(Voucher).filter_by(id=vid).first()
            if not voucher:
                invalid_vouchers.append({
                    "id": vid,
                    "reason": "凭证记录不存在",
                    "date": ""
                })
                continue

            # 自动推断小分类
            if not voucher.sub_expense_type:
                voucher.sub_expense_type = _determine_voucher_sub_expense_type(voucher) or None

            invalid_reasons = []

            # 1) 90天时效性校验
            timeliness_reason = _check_timeliness(voucher.payment_date)
            if timeliness_reason:
                invalid_reasons.append(timeliness_reason)

            # 2) 按费用类型进行金额合规检查
            adapter = _VoucherAsInvoice(voucher)
            amount_reason = _check_expense_amount(expense_type, adapter, user_role, employee_id, db)
            if amount_reason:
                invalid_reasons.append(amount_reason)

            invalid_reason = "；".join(invalid_reasons) if invalid_reasons else None

            if invalid_reason:
                voucher.is_valid = False
                voucher.invalid_reason = invalid_reason
                invalid_vouchers.append({
                    "id": vid,
                    "reason": invalid_reason,
                    "date": voucher.payment_date
                })
            else:
                voucher.is_valid = True
                voucher.invalid_reason = None
                valid_vouchers.append(voucher)

        db.commit()

        valid_total = sum(v.amount for v in valid_vouchers)

        result = f"凭证合规审查完成。\n"
        result += f"费用类型：{expense_type} | 申请人职级：{_role_display(user_role)}\n"
        result += f"合规凭证：{len(valid_vouchers)} 张，合计金额 {valid_total:,.2f} 元\n"

        if invalid_vouchers:
            result += f"不合规凭证：{len(invalid_vouchers)} 张\n"
            for v in invalid_vouchers:
                result += f"  - 凭证 ID {v['id']}：{v['reason']}\n"

        result += f"本次可报销金额：{valid_total:,.2f} 元"

        return result

    except ValueError:
        return "错误：凭证ID列表格式不正确，请确保为数字，用逗号分隔"
    except Exception as e:
        db.rollback()
        return f"凭证合规审查失败：{str(e)}"
    finally:
        db.close()


@tool("更新发票描述")
def update_invoice_description(invoice_id: int, description: str) -> str:
    """
    更新发票的描述信息，按票据类型规范填写。格式要求：
    - 住宿：入住日期至退房日期、房型，如"入住2026-06-01至2026-06-09，标准单人间"
    - 火车票：出发地→目的地、座位类型，如"北京→上海，二等座"
    - 机票：出发地→目的地、舱位，如"北京→上海，经济舱"
    - 出租车/网约车：行程描述，如"客户拜访，公司→XX公司"
    - 餐饮：用餐人数及事由，如"招待客户3人，项目洽谈"
    - 礼品：礼品名称及收礼方，如"茶叶礼盒，赠送XX客户"
    :param invoice_id: 发票记录ID
    :param description: 规范的描述文本
    :return: 更新结果字符串
    """
    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter_by(id=invoice_id).first()
        if not invoice:
            return f"错误：未找到ID为 {invoice_id} 的发票记录"
        invoice.description = description
        invoice.updated_at = datetime.now()
        db.commit()
        return f"发票ID {invoice_id} 描述已更新：{description}"
    except Exception as e:
        db.rollback()
        return f"更新发票描述失败：{str(e)}"
    finally:
        db.close()


def _role_display(role):
    """角色中文显示名"""
    return {
        "employee": "基层员工",
        "manager": "部门经理",
        "director": "总监",
        "general_manager": "总经理",
        "admin": "管理员",
    }.get(role, role)


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
    result = """公司报销政策说明：

一、差旅费（出差公务交通 + 住宿 + 餐补）

1. 出差交通标准（按职级）：
   - 基层员工：高铁二等座，飞机经济舱≤1000元/程，市内交通50元/天，长途汽车实报
   - 部门经理：商务座，商务舱，市内交通实报无上限
   - 总监/总经理：商务座/特等座，头等舱，市内交通实报无上限
   补充：跨城打车、私家车油费仅限紧急客户拜访，需提前报备

2. 住宿标准（按城市分级，元/晚）：
   ┌──────────�──────�──────�──────�──────┐
   │ 城市等级  │基层  │经理  │总监  │总经理│
   ├──────────┼──────┼──────┼──────┼──────┤
   │ 一线城市  │ 350  │ 500  │ 650  │无上限│
   │ 二线省会  │ 280  │ 400  │ 520  │无上限│
   │ 三四线    │ 220  │ 320  │ 420  │无上限│
   └──────────┴──────┴──────┴──────┴──────┘
   补充：双人同性出差合住标间，超标自理

3. 出差餐补（无需发票，按出差自然天数）：
   - 基层员工：80元/天
   - 管理层（经理/总监/总经理）：180元/天
   - 公务宴请或已报餐饮发票的当天不发餐补

二、业务招待费
   - 单人接待人均100元，多人聚餐人均≤150元
   - 单次总额>1000元需总监提前审批
   - 礼品单份≤300元，月度同客户累计≤1000元
   - 烟酒类礼品原则上不予报销

三、日常交通费
   - 通勤打车/私家车油费：不予报销
   - 市内公务外出：月度上限300元
   - 停车费/高速费：仅公务出行，附行程记录

四、办公用品
   - 仅行政部员工集中采购报销，其他员工不可报销

五、其他费用（快递、打印）
   - 实报实销

审批流程：
   - <2000元：部门经理审批
   - 2000~10000元：部门经理 + 总监审批
   - ≥10000元：部门经理 + 总监 + 总经理审批
"""
    return result
