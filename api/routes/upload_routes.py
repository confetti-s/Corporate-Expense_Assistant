"""文件上传 API 路由"""
import os
import uuid
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from api.auth import get_current_user
from config import UPLOADS_DIR

router = APIRouter(prefix="/api/upload", tags=["upload"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}


@router.post("/invoice")
async def upload_invoice(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """上传发票文件，返回服务器端文件路径"""
    ext = os.path.splitext(file.filename or ".jpg")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"不支持的文件类型: {ext}，仅支持 {', '.join(ALLOWED_EXTENSIONS)}")

    dest_dir = os.path.join(UPLOADS_DIR, "invoices")
    os.makedirs(dest_dir, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest_path = os.path.join(dest_dir, safe_name)

    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    return {
        "success": True,
        "file_path": os.path.abspath(dest_path),
        "filename": file.filename,
        "size": len(content),
    }


@router.post("/invoices")
async def upload_invoices(
    files: list[UploadFile] = File(...),
    user: dict = Depends(get_current_user),
):
    """批量上传发票文件"""
    results = []
    for file in files:
        ext = os.path.splitext(file.filename or ".jpg")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            results.append({"success": False, "filename": file.filename, "error": f"不支持的文件类型: {ext}"})
            continue

        dest_dir = os.path.join(UPLOADS_DIR, "invoices")
        os.makedirs(dest_dir, exist_ok=True)

        safe_name = f"{uuid.uuid4().hex}_{file.filename}"
        dest_path = os.path.join(dest_dir, safe_name)

        content = await file.read()
        with open(dest_path, "wb") as f:
            f.write(content)

        results.append({
            "success": True,
            "file_path": os.path.abspath(dest_path),
            "filename": file.filename,
            "size": len(content),
        })

    return {"files": results}
