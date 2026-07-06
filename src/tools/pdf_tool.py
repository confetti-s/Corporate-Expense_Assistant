from langchain.tools import tool
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime
import json
import os
from config import OUTPUTS_DIR

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

    # 发票明细
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
