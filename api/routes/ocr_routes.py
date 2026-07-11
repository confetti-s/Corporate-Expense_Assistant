"""OCR 识别 API 路由 - 直接调用 OCR，不经过 AI Agent"""
import os
import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from api.auth import get_current_user
from src.tools.ocr_tool import ocr_invoice, batch_ocr_invoices
from src.db.database import SessionLocal
from src.db.models import Invoice

router = APIRouter(prefix="/api/ocr", tags=["ocr"])


class OcrRequest(BaseModel):
    file_path: str


class BatchOcrRequest(BaseModel):
    file_paths: list[str]


def _query_invoices_by_ids(invoice_ids: list[int]) -> list[dict]:
    """根据 ID 列表查询发票记录，返回结构化数据"""
    if not invoice_ids:
        return []

    db = SessionLocal()
    try:
        records = db.query(Invoice).filter(Invoice.id.in_(invoice_ids)).all()
        return [_invoice_to_dict(r) for r in records]
    finally:
        db.close()


def _invoice_to_dict(inv: Invoice) -> dict:
    """将 Invoice ORM 对象转为 dict"""
    return {
        "invoice_id": inv.id,
        "type": inv.invoice_type or "",
        "type_name": inv.invoice_type_name or "",
        "amount": float(inv.amount or 0),
        "invoice_code": inv.invoice_code or "",
        "invoice_number": inv.invoice_number or "",
        "invoice_date": inv.invoice_date or "",
        "seller_name": inv.seller_name or "",
        "seller_tax_id": inv.seller_tax_id or "",
        "buyer_name": inv.buyer_name or "",
        "buyer_tax_id": inv.buyer_tax_id or "",
        "probability": inv.confidence or "",
    }


def _extract_invoice_ids(markdown: str) -> list[int]:
    """从 OCR 结果 markdown 中提取发票记录 ID"""
    ids = []
    for m in re.finditer(r"发票记录ID：#(\d+)", markdown):
        try:
            ids.append(int(m.group(1)))
        except ValueError:
            pass
    return ids


@router.post("/invoice")
async def recognize_invoice(req: OcrRequest, user: dict = Depends(get_current_user)):
    """直接识别单张发票，返回结构化发票数据和 Markdown"""
    if not os.path.exists(req.file_path):
        raise HTTPException(400, f"文件不存在: {req.file_path}")

    markdown = ocr_invoice.func(req.file_path, uploaded_by=user.get("sub", ""))
    invoice_ids = _extract_invoice_ids(markdown)
    invoices = _query_invoices_by_ids(invoice_ids)

    return {
        "success": True,
        "invoices": invoices,
        "markdown": markdown,
    }


@router.post("/invoices")
async def recognize_invoices(req: BatchOcrRequest, user: dict = Depends(get_current_user)):
    """直接批量识别发票，返回结构化发票数据和 Markdown"""
    for fp in req.file_paths:
        if not os.path.exists(fp):
            raise HTTPException(400, f"文件不存在: {fp}")

    file_paths_str = ",".join(req.file_paths)
    markdown = batch_ocr_invoices.func(file_paths_str, uploaded_by=user.get("sub", ""))
    invoice_ids = _extract_invoice_ids(markdown)
    invoices = _query_invoices_by_ids(invoice_ids)

    return {
        "success": True,
        "invoices": invoices,
        "markdown": markdown,
    }
