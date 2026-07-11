"""凭证 OCR 识别 API 路由 - 直接调用凭证识别，不经过 AI Agent"""
import os
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from api.auth import get_current_user
from src.tools.voucher_tool import recognize_voucher
from src.db.database import SessionLocal
from src.db.models import Voucher

router = APIRouter(prefix="/api/ocr", tags=["ocr"])


class VoucherOcrRequest(BaseModel):
    file_path: str


class BatchVoucherOcrRequest(BaseModel):
    file_paths: list[str]


def _query_vouchers_by_ids(voucher_ids: list[int]) -> list[dict]:
    if not voucher_ids:
        return []

    db = SessionLocal()
    try:
        records = db.query(Voucher).filter(Voucher.id.in_(voucher_ids)).all()
        return [_voucher_to_dict(r) for r in records]
    finally:
        db.close()


def _voucher_to_dict(v: Voucher) -> dict:
    return {
        "voucher_id": v.id,
        "voucher_type": v.voucher_type or "",
        "amount": float(v.amount or 0),
        "payment_date": v.payment_date or "",
        "payee": v.payee or "",
        "description": v.description or "",
        "ocr_result": v.ocr_result or "",
    }


def _extract_voucher_ids(markdown: str) -> list[int]:
    ids = []
    for m in re.finditer(r"凭证编号.*?#(\d+)", markdown):
        try:
            ids.append(int(m.group(1)))
        except ValueError:
            pass
    return ids


@router.post("/voucher")
async def recognize_voucher_endpoint(req: VoucherOcrRequest, user: dict = Depends(get_current_user)):
    """直接识别单张凭证，返回结构化数据和 Markdown"""
    if not os.path.exists(req.file_path):
        raise HTTPException(400, f"文件不存在: {req.file_path}")

    markdown = recognize_voucher.func(req.file_path, uploaded_by=user.get("sub", ""))
    voucher_ids = _extract_voucher_ids(markdown)
    vouchers = _query_vouchers_by_ids(voucher_ids)

    return {
        "success": True,
        "vouchers": vouchers,
        "markdown": markdown,
    }


@router.post("/vouchers")
async def recognize_vouchers_endpoint(req: BatchVoucherOcrRequest, user: dict = Depends(get_current_user)):
    """批量识别凭证，返回结构化数据和 Markdown"""
    for fp in req.file_paths:
        if not os.path.exists(fp):
            raise HTTPException(400, f"文件不存在: {fp}")

    all_vouchers = []
    markdown_parts = []

    for file_path in req.file_paths:
        try:
            md = recognize_voucher.func(file_path, uploaded_by=user.get("sub", ""))
            markdown_parts.append(md)
            v_ids = _extract_voucher_ids(md)
            vouchers = _query_vouchers_by_ids(v_ids)
            for v in vouchers:
                v["file"] = os.path.basename(file_path)
            all_vouchers.extend(vouchers)
        except Exception as e:
            all_vouchers.append({
                "voucher_id": None,
                "voucher_type": "识别失败",
                "amount": 0.0,
                "payment_date": "",
                "payee": "",
                "description": f"识别失败: {str(e)}",
                "ocr_result": "",
                "file": os.path.basename(file_path),
            })
            markdown_parts.append(f"### 凭证：{os.path.basename(file_path)}\n识别失败：{str(e)}")

    markdown = "\n\n---\n\n".join(markdown_parts)

    return {
        "success": True,
        "vouchers": all_vouchers,
        "markdown": markdown,
    }
