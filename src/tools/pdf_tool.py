from langchain.tools import tool
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, PageBreak
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
import json
import os
from config import OUTPUTS_DIR
from src.db.database import SessionLocal
from src.db.models import Invoice, Voucher

# 注册中文字体
_FONT_REGISTERED = False
CN_FONT = 'Helvetica'

def _ensure_font_registered():
    global _FONT_REGISTERED, CN_FONT
    if _FONT_REGISTERED:
        return
    _FONT_REGISTERED = True
    font_paths = [
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                pdfmetrics.registerFont(TTFont('SimHei', fp))
                CN_FONT = 'SimHei'
                return
            except Exception:
                continue


@tool("生成报销单PDF")
def generate_reimbursement_pdf(
    reimbursement_no: str,
    employee_name: str,
    department: str,
    expense_type: str,
    total_amount: float,
    description: str = "",
    invoice_details_json: str = "[]"
) -> str:
    """
    生成标准化的报销单PDF文件
    :param reimbursement_no: 报销单号
    :param employee_name: 员工姓名
    :param department: 部门名称
    :param expense_type: 费用类型
    :param total_amount: 总金额
    :param description: 备注说明（可选）
    :param invoice_details_json: 发票明细JSON数组字符串（可选）
    :return: PDF文件路径
    """
    _ensure_font_registered()
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

    pdf_path = os.path.join(OUTPUTS_DIR, f"reimbursement_{reimbursement_no}.pdf")

    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                            leftMargin=25*mm, rightMargin=25*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle('Title', parent=styles['Heading1'],
                                  alignment=1, fontSize=18, spaceAfter=20,
                                  fontName=CN_FONT)
    heading_style = ParagraphStyle('Heading2', parent=styles['Heading2'],
                                    fontSize=13, spaceAfter=8, fontName=CN_FONT)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'],
                                   fontSize=11, spaceAfter=6, fontName=CN_FONT)

    elements.append(Paragraph("企业财务报销单", title_style))
    elements.append(Spacer(1, 15))

    # 基本信息
    data = [
        ["报销单号", reimbursement_no, "申请日期", datetime.now().strftime('%Y-%m-%d')],
        ["员工姓名", employee_name, "所属部门", department],
        ["费用类型", expense_type, "报销金额", f"{total_amount:,.2f} 元"],
        ["备注", description if description else "-", "", ""],
    ]
    t = Table(data, colWidths=[80, 150, 80, 150])
    t.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), CN_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#E3F2FD')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#E3F2FD')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('SPAN', (1, 3), (3, 3)),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 15))

    # 发票明细：优先从Invoice表读取，降级用invoice_details_json
    invoices = []
    try:
        db = SessionLocal()
        db_invoices = db.query(Invoice).filter_by(reimbursement_no=reimbursement_no).all()
        if db_invoices:
            invoices = [
                {
                    "type_name": inv.invoice_type_name or "-",
                    "amount": inv.amount or 0,
                    "invoice_code": inv.invoice_code or "-",
                    "seller_name": inv.seller_name or "-",
                }
                for inv in db_invoices
            ]
        db.close()
    except Exception:
        pass

    if not invoices:
        try:
            invoices = json.loads(invoice_details_json) if invoice_details_json else []
        except (json.JSONDecodeError, TypeError):
            invoices = []

    if invoices:
        elements.append(Paragraph("发票明细", heading_style))
        inv_header = ["序号", "发票类型", "金额(元)", "发票代码", "销售方名称"]
        inv_data = [inv_header]
        for idx, inv in enumerate(invoices, 1):
            inv_data.append([
                str(idx),
                inv.get("type_name", "-"),
                f"{inv.get('amount', 0):,.2f}",
                inv.get("invoice_code", "-"),
                inv.get("seller_name", "-"),
            ])
        inv_table = Table(inv_data, colWidths=[40, 100, 80, 120, 120])
        inv_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), CN_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8F5E9')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(inv_table)
        elements.append(Spacer(1, 15))

    # 凭证明细：从Voucher表读取
    vouchers = []
    try:
        db = SessionLocal()
        db_vouchers = db.query(Voucher).filter_by(reimbursement_no=reimbursement_no).all()
        if db_vouchers:
            vouchers = [
                {
                    "voucher_type": v.voucher_type or "-",
                    "amount": v.amount or 0,
                    "payment_date": v.payment_date or "-",
                    "payee": v.payee or "-",
                }
                for v in db_vouchers
            ]
        db.close()
    except Exception:
        pass

    if vouchers:
        elements.append(Paragraph("凭证明细", heading_style))
        v_header = ["序号", "凭证类型", "金额(元)", "交易日期", "收款方"]
        v_data = [v_header]
        for idx, v in enumerate(vouchers, 1):
            v_data.append([
                str(idx),
                v.get("voucher_type", "-"),
                f"{v.get('amount', 0):,.2f}",
                v.get("payment_date", "-"),
                v.get("payee", "-"),
            ])
        v_table = Table(v_data, colWidths=[40, 120, 80, 100, 120])
        v_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), CN_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8EAF6')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(v_table)
        elements.append(Spacer(1, 15))

    # 附件图片区：发票+凭证图片
    image_paths = []
    try:
        db = SessionLocal()
        # 收集发票图片
        db_invoices = db.query(Invoice).filter_by(reimbursement_no=reimbursement_no).all()
        for inv in db_invoices:
            if inv.file_path and os.path.exists(inv.file_path):
                image_paths.append(("发票", inv.file_path))
        # 收集凭证图片
        db_vouchers = db.query(Voucher).filter_by(reimbursement_no=reimbursement_no).all()
        for v in db_vouchers:
            if v.file_path and os.path.exists(v.file_path):
                image_paths.append(("凭证", v.file_path))
        db.close()
    except Exception:
        pass

    if image_paths:
        elements.append(Paragraph("附件图片", heading_style))
        available_width = A4[0] - 50 * mm  # 页面宽度减去左右边距
        for label, img_path in image_paths:
            try:
                img = RLImage(img_path)
                img_w, img_h = img.drawWidth, img.drawHeight
                # 缩放：宽度不超过可用宽度，高度不超过200mm
                scale = min(available_width / img_w, 200 * mm / img_h, 1.0)
                img.drawWidth = img_w * scale
                img.drawHeight = img_h * scale
                elements.append(Paragraph(f"{label}：{os.path.basename(img_path)}", normal_style))
                elements.append(img)
                elements.append(Spacer(1, 10))
            except Exception:
                elements.append(Paragraph(f"{label}：{os.path.basename(img_path)}（图片加载失败）", normal_style))

    # 审批流程
    elements.append(Paragraph("审批流程", heading_style))
    approval_data = [
        ["审批环节", "审批人", "签字", "日期"],
        ["部门审批", "", "", ""],
        ["财务审核", "", "", ""],
        ["领导审批", "", "", ""],
    ]
    approval_table = Table(approval_data, colWidths=[100, 120, 120, 120])
    approval_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), CN_FONT),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#FFF3E0')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
    ]))
    elements.append(approval_table)
    elements.append(Spacer(1, 25))

    elements.append(Paragraph(f"申请人签字：___________    日期：{datetime.now().strftime('%Y-%m-%d')}", normal_style))

    doc.build(elements)
    return f"报销单PDF已生成：{pdf_path}"


def auto_generate_pdf(reimbursement_no: str) -> str:
    """根据报销单号自动从DB取数据生成PDF，返回文件路径，失败返回空字符串"""
    from src.db.models import Reimbursements, DepartmentBudget
    db = SessionLocal()
    try:
        reimb = db.query(Reimbursements).filter_by(reimbursement_no=reimbursement_no).first()
        if not reimb:
            print(f"[PDF] 未找到报销单 {reimbursement_no}")
            return ""

        dept = db.query(DepartmentBudget).filter_by(department_id=reimb.department_id).first()
        dept_name = dept.department_name if dept else reimb.department_id or ""

        result = generate_reimbursement_pdf.func(
            reimbursement_no=reimb.reimbursement_no,
            employee_name=reimb.employee_name,
            department=dept_name,
            expense_type=reimb.expense_type,
            total_amount=reimb.total_amount,
            description=reimb.description or "",
            invoice_details_json=reimb.invoice_details or "[]"
        )
        if "已生成：" in result:
            return result.split("已生成：")[1].strip()
        print(f"[PDF] 生成结果: {result}")
        return ""
    except Exception as e:
        print(f"[PDF] 自动生成失败: {e}")
        return ""
    finally:
        db.close()
