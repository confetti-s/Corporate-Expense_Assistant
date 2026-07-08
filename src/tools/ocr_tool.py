from langchain.tools import tool
import requests
import base64
import json
import os
from config import BAIDU_OCR_API_KEY, BAIDU_OCR_SECRET_KEY, BAIDU_OCR_TOKEN_URL, BAIDU_OCR_API_URL
from src.db.database import SessionLocal
from src.db.models import Invoice

_access_token = None
_token_expire_time = 0

def get_access_token():
    global _access_token, _token_expire_time
    import time
    if _access_token and time.time() < _token_expire_time:
        return _access_token
    
    params = {
        "grant_type": "client_credentials",
        "client_id": BAIDU_OCR_API_KEY,
        "client_secret": BAIDU_OCR_SECRET_KEY
    }
    
    try:
        response = requests.post(BAIDU_OCR_TOKEN_URL, params=params)
        response.raise_for_status()
        result = response.json()
        
        if "access_token" in result:
            _access_token = result["access_token"]
            _token_expire_time = time.time() + result.get("expires_in", 3600) - 60
            return _access_token
        else:
            raise ValueError(f"获取access_token失败: {result}")
    except Exception as e:
        raise RuntimeError(f"获取access_token异常: {str(e)}")

def encode_image(file_path):
    with open(file_path, "rb") as f:
        image_data = f.read()
    return base64.b64encode(image_data).decode("utf-8")

INVOICE_TYPE_MAP = {
    "vat_invoice": "增值税发票",
    "taxi_receipt": "出租车票",
    "train_ticket": "火车票",
    "quota_invoice": "定额发票",
    "air_ticket": "飞机行程单",
    "roll_normal_invoice": "卷票",
    "printed_invoice": "机打发票",
    "printed_elec_invoice": "机打电子发票",
    "bus_ticket": "汽车票",
    "toll_invoice": "过路过桥费发票",
    "ferry_ticket": "船票",
    "motor_vehicle_invoice": "机动车销售发票",
    "used_vehicle_invoice": "二手车销售发票",
    "taxi_online_ticket": "网约车行程单",
    "limit_invoice": "限额发票",
    "shopping_receipt": "购物小票",
    "pos_invoice": "POS小票",
    "others": "其他"
}

def _extract_field(result_dict, key, default=""):
    """从 multiple_invoice API 返回的字段中提取文本值。
    API 返回格式: {"AmountInFiguers": [{"word": "5200.00", "probability": {...}}]}
    """
    val = result_dict.get(key, default)
    if isinstance(val, list) and len(val) > 0:
        return val[0].get("word", default)
    if isinstance(val, str):
        return val
    return default


def _save_invoice_to_db(invoice_data, file_path="", uploaded_by=""):
    """将OCR识别的发票数据存入Invoice表，返回invoice_id"""
    db = SessionLocal()
    try:
        record = Invoice(
            invoice_code=invoice_data.get("invoice_code", ""),
            invoice_number=invoice_data.get("invoice_number", ""),
            invoice_type=invoice_data.get("type", ""),
            invoice_type_name=invoice_data.get("type_name", ""),
            amount=invoice_data.get("amount", 0.0),
            invoice_date=invoice_data.get("invoice_date", ""),
            seller_name=invoice_data.get("seller_name", ""),
            seller_tax_id=invoice_data.get("seller_tax_id", ""),
            buyer_name=invoice_data.get("buyer_name", ""),
            buyer_tax_id=invoice_data.get("buyer_tax_id", ""),
            confidence=invoice_data.get("probability", ""),
            file_path=file_path,
            uploaded_by=uploaded_by or None,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.id
    except Exception as e:
        db.rollback()
        print(f"[Invoice保存失败] {e}")
        return None
    finally:
        db.close()


def parse_invoice_result(result):
    invoice_type = result.get("type", "others")
    type_name = INVOICE_TYPE_MAP.get(invoice_type, "未知票据")
    invoice_result = result.get("result", {})

    amount_str = _extract_field(invoice_result, "AmountInFiguers")
    raw_code = _extract_field(invoice_result, "InvoiceCode")
    raw_number = _extract_field(invoice_result, "InvoiceNum")

    # 电子发票：发票代码为空，发票号码为20位（前12位=代码，后8位=号码）
    if not raw_code and raw_number and len(raw_number) == 20 and raw_number.isdigit():
        invoice_code = raw_number[:12]
        invoice_number = raw_number[12:]
    else:
        invoice_code = raw_code
        invoice_number = raw_number
    invoice_date = _extract_field(invoice_result, "InvoiceDate")
    seller_name = _extract_field(invoice_result, "SellerName")
    seller_tax_id = _extract_field(invoice_result, "SellerRegisterNum")
    buyer_name = _extract_field(invoice_result, "PurchaserName")
    buyer_tax_id = _extract_field(invoice_result, "PurchaserRegisterNum")

    prob_info = result.get("probability", {})
    if isinstance(prob_info, dict):
        probability = f"{prob_info.get('average', 0):.4f}"
    else:
        probability = str(prob_info)

    try:
        amount = float(amount_str.replace(",", "")) if amount_str else 0.0
    except ValueError:
        amount = 0.0

    return {
        "type": invoice_type,
        "type_name": type_name,
        "amount": amount,
        "invoice_code": invoice_code,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "seller_name": seller_name,
        "seller_tax_id": seller_tax_id,
        "buyer_name": buyer_name,
        "buyer_tax_id": buyer_tax_id,
        "probability": probability
    }

def _is_pdf(file_path: str) -> bool:
    return file_path.lower().endswith('.pdf')


def _encode_file(file_path: str) -> bytes:
    """读取文件并base64编码（支持图片和PDF）"""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read())


def _call_ocr_api(file_path: str) -> dict:
    """调用百度OCR multiple_invoice API，自动区分图片和PDF"""
    access_token = get_access_token()
    encoded_data = _encode_file(file_path)
    url = f"{BAIDU_OCR_API_URL}?access_token={access_token}"

    if _is_pdf(file_path):
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"pdf_file": encoded_data.decode("utf-8")}
        data["pdf_file_num"] = "1"
    else:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"image": encoded_data.decode("utf-8")}

    data["verify_parameter"] = "false"
    data["probability"] = "true"
    data["location"] = "false"

    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()
    return response.json()


@tool("票据OCR识别")
def ocr_invoice(file_path: str, uploaded_by: str = "") -> str:
    """
    使用百度智能云识别票据图片或PDF中的发票信息，识别结果自动存入发票表
    :param file_path: 文件路径，支持图片（jpg/jpeg/png/bmp）和PDF格式
    :param uploaded_by: 上传人用户ID（可选，如E001）
    :return: 结构化的发票信息字符串（含发票记录ID，用于后续创建报销单时关联）
    """
    if not BAIDU_OCR_API_KEY or not BAIDU_OCR_SECRET_KEY:
        return "错误：百度OCR API密钥未配置，请在.env文件中设置BAIDU_OCR_API_KEY和BAIDU_OCR_SECRET_KEY"

    try:
        result = _call_ocr_api(file_path)

        if result.get("words_result_num", 0) > 0:
            invoice_data = parse_invoice_result(result["words_result"][0])

            # 存入Invoice表
            invoice_id = _save_invoice_to_db(invoice_data, file_path=file_path, uploaded_by=uploaded_by)

            id_hint = f"\n发票记录ID：{invoice_id}" if invoice_id else ""
            
            date_hint = f"\n\n⚠️ 注意：开票日期未能识别，请提供该发票的开票日期（格式：YYYY-MM-DD），以便我为您补录。" if not invoice_data['invoice_date'] else ""

            return f"""票据识别结果：
票据类型：{invoice_data['type_name']}
置信度：{invoice_data['probability']}
发票代码：{invoice_data['invoice_code']}
发票号码：{invoice_data['invoice_number']}
金额：{invoice_data['amount']:,.2f} 元
开票日期：{invoice_data['invoice_date']}
销售方名称：{invoice_data['seller_name']}
销售方税号：{invoice_data['seller_tax_id']}
购买方名称：{invoice_data['buyer_name']}
购买方税号：{invoice_data['buyer_tax_id']}{id_hint}{date_hint}"""
        else:
            return "识别结果为空，未检测到票据"
            
    except Exception as e:
        return f"票据识别失败：{str(e)}"

@tool("批量票据识别")
def batch_ocr_invoices(file_paths: str, uploaded_by: str = "") -> str:
    """
    批量识别多张票据，识别结果自动存入发票表
    :param file_paths: 文件路径列表，用逗号分隔
    :param uploaded_by: 上传人用户ID（可选，如E001）
    :return: 所有票据的识别结果字符串（含发票记录ID）
    """
    if not BAIDU_OCR_API_KEY or not BAIDU_OCR_SECRET_KEY:
        return "错误：百度OCR API密钥未配置，请在.env文件中设置BAIDU_OCR_API_KEY和BAIDU_OCR_SECRET_KEY"
    
    files = [f.strip() for f in file_paths.split(',') if f.strip()]
    results = []
    
    for file_path in files:
        try:
            result = _call_ocr_api(file_path)
            
            if result.get("words_result_num", 0) > 0:
                invoice_data = parse_invoice_result(result["words_result"][0])
                inv_id = _save_invoice_to_db(invoice_data, file_path=file_path, uploaded_by=uploaded_by)
                results.append({
                    "file": os.path.basename(file_path),
                    "type_name": invoice_data["type_name"],
                    "probability": invoice_data["probability"],
                    "amount": invoice_data["amount"],
                    "invoice_code": invoice_data["invoice_code"],
                    "invoice_number": invoice_data["invoice_number"],
                    "invoice_date": invoice_data["invoice_date"],
                    "seller_name": invoice_data["seller_name"],
                    "seller_tax_id": invoice_data["seller_tax_id"],
                    "buyer_name": invoice_data["buyer_name"],
                    "buyer_tax_id": invoice_data["buyer_tax_id"],
                    "invoice_id": inv_id
                })
            else:
                results.append({
                    "file": os.path.basename(file_path),
                    "type_name": "未识别",
                    "probability": "",
                    "amount": 0.0,
                    "invoice_code": "",
                    "invoice_number": "",
                    "invoice_date": "",
                    "seller_name": "",
                    "seller_tax_id": "",
                    "buyer_name": "",
                    "buyer_tax_id": ""
                })
        except Exception as e:
            results.append({
                "file": os.path.basename(file_path),
                "type_name": f"识别失败: {str(e)}",
                "probability": "",
                "amount": 0.0,
                "invoice_code": "",
                "invoice_number": "",
                "invoice_date": "",
                "seller_name": "",
                "seller_tax_id": "",
                "buyer_name": "",
                "buyer_tax_id": ""
            })
    
    total_amount = sum(r["amount"] for r in results)
    
    missing_date_items = []
    for i, r in enumerate(results):
        if not r['invoice_date'] and r.get('invoice_id'):
            missing_date_items.append(f"票据 {i + 1}（发票记录ID：{r['invoice_id']}）")
    
    result_str = f"批量识别结果（共 {len(results)} 张票据）：\n\n"
    for i, r in enumerate(results):
        id_hint = f"| 发票记录ID | {r['invoice_id']} |\n" if r.get('invoice_id') else ""
        date_warning = f"| ⚠️ 缺少日期 | 请补充开票日期 |\n" if not r['invoice_date'] else ""
        result_str += f"""**票据 {i + 1}**

| 项目 | 内容 |
|------|------|
| 文件 | {r['file']} |
| 票据类型 | {r['type_name']} |
| 置信度 | {r['probability']} |
| 发票代码 | {r['invoice_code']} |
| 发票号码 | {r['invoice_number']} |
| 金额 | {r['amount']:,.2f} 元 |
| 开票日期 | {r['invoice_date']} |
| 销售方名称 | {r['seller_name']} |
| 销售方税号 | {r['seller_tax_id']} |
| 购买方名称 | {r['buyer_name']} |
| 购买方税号 | {r['buyer_tax_id']} |
{id_hint}{date_warning}
"""
    
    if missing_date_items:
        result_str += f"\n⚠️ 以下票据缺少开票日期，请提供对应日期（格式：YYYY-MM-DD）：\n"
        for item in missing_date_items:
            result_str += f"- {item}\n"
    
    result_str += f"\n**总金额：{total_amount:,.2f} 元**"
    
    return result_str


@tool("更新发票日期")
def update_invoice_date(invoice_id: int, invoice_date: str) -> str:
    """
    更新发票记录的开票日期，用于补录OCR未能识别的日期
    :param invoice_id: 发票记录ID（OCR识别时返回的发票记录ID）
    :param invoice_date: 开票日期，格式为YYYY-MM-DD（如2024-01-15）
    :return: 更新结果提示
    """
    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter_by(id=invoice_id).first()
        if not invoice:
            return f"错误：未找到发票记录ID为 {invoice_id} 的发票"
        
        invoice.invoice_date = invoice_date
        db.commit()
        return f"成功：发票记录ID {invoice_id} 的开票日期已更新为 {invoice_date}"
    except Exception as e:
        db.rollback()
        return f"更新失败：{str(e)}"
    finally:
        db.close()