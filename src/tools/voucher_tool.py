from langchain.tools import tool
import requests
import base64
import json
import os
import re
from config import BAIDU_OCR_API_KEY, BAIDU_OCR_SECRET_KEY, BAIDU_GENERAL_OCR_API_URL, UPLOADS_DIR
from src.db.database import SessionLocal
from src.db.models import Voucher
from src.tools.ocr_tool import get_access_token, _encode_file, _persist_file


def _extract_amount_from_text(text: str) -> float:
    """从OCR文本中提取金额"""
    patterns = [
        r'[￥¥]\s*([\d,]+\.?\d*)',
        r'金额[：:]\s*([\d,]+\.?\d*)',
        r'([\d,]+\.?\d*)\s*元',
        r'支付[：:]\s*([\d,]+\.?\d*)',
        r'转账[：:]\s*([\d,]+\.?\d*)',
        r'付款[：:]\s*([\d,]+\.?\d*)',
        r'^-([\d,]+\.?\d*)$',       # 独立一行的负数金额如 -28.80
        r'商户全称.*?\n.*?-([\d,]+\.?\d*)',  # 商户名下一行的负数金额
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            try:
                return abs(float(match.group(1).replace(",", "")))
            except ValueError:
                continue
    # 兜底：查找所有独立数字行，取最大的合理金额
    for line in text.split('\n'):
        line = line.strip()
        m = re.match(r'^-?([\d,]+\.\d{1,2})$', line)
        if m:
            try:
                val = abs(float(m.group(1).replace(",", "")))
                if 0 < val < 1000000:
                    return val
            except ValueError:
                continue
    return 0.0


def _extract_date_from_text(text: str) -> str:
    """从OCR文本中提取日期"""
    patterns = [
        r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}[日]?)',
        r'(\d{4}\.\d{1,2}\.\d{1,2})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            date_str = date_str.replace('年', '-').replace('月', '-').replace('日', '').replace('/', '-').replace('.', '-')
            return date_str
    return ""


def _extract_payee_from_text(text: str) -> str:
    """从OCR文本中提取收款方"""
    patterns = [
        r'收款[方人][：:]\s*(.+)',
        r'收款[方人]\s+(.+)',
        r'转给[：:]\s*(.+)',
        r'付款给[：:]\s*(.+)',
        r'对方[：:]\s*(.+)',
        r'商户全称[：:]*\s*\n?\s*(.+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            payee = match.group(1).strip()
            if len(payee) > 50:
                payee = payee[:50]
            return payee
    return ""


def _build_kv_by_position(words_result: list) -> dict:
    """利用位置信息构建键值对：同一行(上下接近)的文字视为key-value对"""
    items = []
    for w in words_result:
        loc = w.get("location", {})
        items.append({
            "text": w.get("words", ""),
            "left": loc.get("left", 0),
            "top": loc.get("top", 0),
            "width": loc.get("width", 0),
            "height": loc.get("height", 0),
        })

    # 按top排序，再按left排序，模拟从上到下从左到右阅读
    items.sort(key=lambda x: (x["top"], x["left"]))

    # 将top接近的文字归为同一行（容差=高度的0.6倍）
    lines = []
    current_line = []
    for item in items:
        if not current_line:
            current_line.append(item)
        else:
            avg_top = sum(it["top"] for it in current_line) / len(current_line)
            avg_height = sum(it["height"] for it in current_line) / len(current_line) or 20
            if abs(item["top"] - avg_top) < avg_height * 0.6:
                current_line.append(item)
            else:
                lines.append(sorted(current_line, key=lambda x: x["left"]))
                current_line = [item]
    if current_line:
        lines.append(sorted(current_line, key=lambda x: x["left"]))

    # 从行中提取键值对：左侧文字为key，右侧文字为value
    kv = {}
    for line in lines:
        if len(line) == 1:
            continue
        # 取最左边的作为key，其余拼接为value
        key = line[0]["text"].strip().rstrip("：:：")
        value = "".join(it["text"] for it in line[1:]).strip()
        if key and value:
            kv[key] = value
    return kv


def _parse_voucher_result(ocr_result: dict) -> dict:
    """解析百度通用文字识别（含位置版）API结果，利用位置信息提取凭证字段"""
    words_result = ocr_result.get("words_result", [])
    full_text = "\n".join([item.get("words", "") for item in words_result])

    # 利用位置信息构建键值对
    kv = _build_kv_by_position(words_result)

    # 构建格式化的OCR原文：键值对每类一行，单独行保留
    lines_kv = []
    used_texts = set()
    for key, value in kv.items():
        lines_kv.append(f"{key}：{value}")
        used_texts.add(key)
        used_texts.add(value)

    # 找出未被kv配对的独立行（如标题、金额等）
    items = []
    for w in words_result:
        text = w.get("words", "").strip()
        loc = w.get("location", {})
        items.append({"text": text, "top": loc.get("top", 0), "left": loc.get("left", 0)})
    items.sort(key=lambda x: (x["top"], x["left"]))

    single_lines = []
    current_line_texts = []
    current_top = None
    for it in items:
        if current_top is None or abs(it["top"] - current_top) < 15:
            current_line_texts.append(it["text"])
            if current_top is None:
                current_top = it["top"]
        else:
            full_line = "".join(current_line_texts).strip()
            if full_line and full_line not in used_texts:
                single_lines.append(full_line)
            current_line_texts = [it["text"]]
            current_top = it["top"]
    if current_line_texts:
        full_line = "".join(current_line_texts).strip()
        if full_line and full_line not in used_texts:
            single_lines.append(full_line)

    formatted_text = "\n".join(single_lines + [""] + lines_kv) if lines_kv else full_text

    # 提取金额：优先从键值对中找，再从原文正则匹配
    amount = 0.0
    for key in ["金额", "支付金额", "实付金额", "交易金额", "付款金额"]:
        if key in kv:
            try:
                amount = abs(float(kv[key].replace(",", "").replace("￥", "").replace("¥", "").replace("元", "").strip()))
                break
            except ValueError:
                continue
    if amount == 0.0:
        amount = _extract_amount_from_text(full_text)

    # 提取日期：优先从键值对找
    payment_date = ""
    for key in ["支付时间", "交易时间", "转账时间", "付款时间", "交易日期", "日期"]:
        if key in kv:
            date_str = kv[key]
            m = re.search(r'(\d{4})[年/\-\.](\d{1,2})[月/\-\.](\d{1,2})', date_str)
            if m:
                payment_date = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
                break
    if not payment_date:
        payment_date = _extract_date_from_text(full_text)

    # 提取收款方：优先从键值对找
    payee = ""
    for key in ["商户全称", "收款方", "收款人", "对方", "付款给", "转给"]:
        if key in kv:
            payee = kv[key].strip()[:50]
            break
    if not payee:
        payee = _extract_payee_from_text(full_text)

    # 凭证类型判断
    if "微信" in full_text or "WeChat" in full_text or "零钱" in full_text or "财付通" in full_text:
        voucher_type = "微信付款截图"
    elif "支付宝" in full_text or "Alipay" in full_text or "花呗" in full_text:
        voucher_type = "支付宝付款截图"
    elif "转账" in full_text or "银行" in full_text:
        voucher_type = "转账记录"
    elif "收据" in full_text or "收条" in full_text:
        voucher_type = "收据"
    else:
        voucher_type = "其他凭证"

    return {
        "voucher_type": voucher_type,
        "amount": amount,
        "payment_date": payment_date,
        "payee": payee,
        "description": "",
        "ocr_result": formatted_text,
    }


def _save_voucher_to_db(voucher_data: dict, file_path: str = "", uploaded_by: str = "") -> int:
    """将凭证数据存入Voucher表，返回voucher_id"""
    db = SessionLocal()
    try:
        record = Voucher(
            voucher_type=voucher_data.get("voucher_type", "其他"),
            amount=voucher_data.get("amount", 0.0),
            payment_date=voucher_data.get("payment_date", ""),
            payee=voucher_data.get("payee", ""),
            description=voucher_data.get("description", ""),
            ocr_result=voucher_data.get("ocr_result", ""),
            file_path=file_path,
            uploaded_by=uploaded_by or None,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record.id
    except Exception as e:
        db.rollback()
        print(f"[Voucher保存失败] {e}")
        return None
    finally:
        db.close()


@tool("凭证识别")
def recognize_voucher(file_path: str, uploaded_by: str = "") -> str:
    """
    使用百度通用文字识别API识别付款截图、转账记录等非发票凭证，识别结果自动存入凭证表
    :param file_path: 凭证图片文件路径（支持jpg/jpeg/png/bmp格式）
    :param uploaded_by: 上传人用户ID（可选，如E001）
    :return: 凭证识别结果字符串（含凭证记录ID，用于后续创建报销单时关联）
    """
    if not BAIDU_OCR_API_KEY or not BAIDU_OCR_SECRET_KEY:
        return "错误：百度OCR API密钥未配置，请在.env文件中设置BAIDU_OCR_API_KEY和BAIDU_OCR_SECRET_KEY"

    try:
        access_token = get_access_token()
        encoded_data = _encode_file(file_path)
        url = f"{BAIDU_GENERAL_OCR_API_URL}?access_token={access_token}"

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"image": encoded_data.decode("utf-8")}

        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        result = response.json()

        words_result_num = result.get("words_result_num", 0)
        if words_result_num > 0:
            voucher_data = _parse_voucher_result(result)

            # 持久化图片文件
            persistent_path = _persist_file(file_path, "vouchers")

            # 存入Voucher表
            voucher_id = _save_voucher_to_db(voucher_data, file_path=persistent_path, uploaded_by=uploaded_by)

            ocr_text = voucher_data['ocr_result'][:300]
            return f"""### 凭证识别结果

| 项目 | 内容 |
|------|------|
| 凭证类型 | {voucher_data['voucher_type']} |
| 金额 | {voucher_data['amount']:,.2f} 元 |
| 交易日期 | {voucher_data['payment_date'] or '未识别'} |
| 收款方 | {voucher_data['payee'] or '未识别'} |
| 凭证编号 | {f'#{voucher_id}' if voucher_id else '—'} |

<details>
<summary>OCR原文</summary>

```
{ocr_text}
```
</details>"""
        else:
            return "凭证识别结果为空，未检测到文字内容"

    except Exception as e:
        return f"凭证识别失败：{str(e)}"
