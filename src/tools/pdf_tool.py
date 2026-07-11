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
from src.db.models import Invoice, Voucher, Reimbursements, ApprovalRecords

# 注册中文字体
_FONT_REGISTERED = False
CN_FONT = 'Helvetica'

def _ensure_font_registered():
    global _FONT_REGISTERED, CN_FONT
    if _FONT_REGISTERED:
        return
    _FONT_REGISTERED = True
    # 优先使用 .ttf 文件，.ttc 文件需要指定 subfontIndex
    font_candidates = [
        (r"C:\Windows\Fonts\simhei.ttf", None),
        (r"C:\Windows\Fonts\simfang.ttf", None),
        (r"C:\Windows\Fonts\simsun.ttc", 0),
        (r"C:\Windows\Fonts\msyh.ttc", 0),
        (r"C:\Windows\Fonts\msyhbd.ttc", 0),
    ]
    for fp, subfont_idx in font_candidates:
        if os.path.exists(fp):
            try:
                kwargs = {'name': 'SimHei', 'filename': fp}
                if subfont_idx is not None:
                    kwargs['subfontIndex'] = subfont_idx
                pdfmetrics.registerFont(TTFont(**kwargs))
                CN_FONT = 'SimHei'
                print(f"[PDF] 成功注册字体: {fp}")
                return
            except Exception as e:
                print(f"[PDF] 注册字体失败 {fp}: {e}")
                continue
    print("[PDF] 警告：未找到可用的中文字体，PDF中文可能显示异常")


def _build_expense_items(reimbursement_no):
    """从数据库读取发票和凭证，构建统一的费用明细列表"""
    db = SessionLocal()
    try:
        items = []
        invoices = db.query(Invoice).filter_by(reimbursement_no=reimbursement_no).all()
        for inv in invoices:
            items.append({
                "sub_expense_type": inv.sub_expense_type or "其他",
                "description": inv.description or "-",
                "date": inv.invoice_date or "-",
                "amount": inv.amount or 0,
                "remark": "发票",
                "ai_suggestion": "合规" if inv.is_valid else f"不合规：{inv.invalid_reason or ''}",
            })
        vouchers = db.query(Voucher).filter_by(reimbursement_no=reimbursement_no).all()
        for v in vouchers:
            items.append({
                "sub_expense_type": v.sub_expense_type or "其他",
                "description": v.description or "-",
                "date": v.payment_date or "-",
                "amount": v.amount or 0,
                "remark": "凭证",
                "ai_suggestion": "合规" if v.is_valid else f"不合规：{v.invalid_reason or ''}",
            })
        return items
    finally:
        db.close()


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
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'],
                                 fontSize=9, leading=12, fontName=CN_FONT, wordWrap='CJK')
    cell_style_center = ParagraphStyle('CellCenter', parent=cell_style, alignment=1)
    header_style_pdf = ParagraphStyle('HeaderCell', parent=cell_style,
                                       fontSize=9, leading=12, fontName=CN_FONT,
                                       textColor=colors.black, alignment=1)
    info_style = ParagraphStyle('InfoCell', parent=styles['Normal'],
                                 fontSize=11, leading=14, fontName=CN_FONT, wordWrap='CJK')

    def _p(text, style=cell_style):
        """将文本转为 Paragraph 对象以支持自动换行"""
        return Paragraph(str(text), style)

    elements.append(Paragraph("企业财务报销单", title_style))
    elements.append(Spacer(1, 15))

    # 基本信息
    data = [
        [_p("报销单号", info_style), _p(reimbursement_no, info_style), _p("申请日期", info_style), _p(datetime.now().strftime('%Y-%m-%d'), info_style)],
        [_p("员工姓名", info_style), _p(employee_name, info_style), _p("所属部门", info_style), _p(department, info_style)],
        [_p("报销类别", info_style), _p(expense_type, info_style), _p("申请总金额", info_style), _p(f"{total_amount:,.2f} 元", info_style)],
        [_p("报销说明", info_style), _p(description if description else "-", info_style), "", ""],
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

    # 统一费用明细表
    items = _build_expense_items(reimbursement_no)
    if items:
        elements.append(Paragraph("费用明细", heading_style))
        header = [_p("序号", header_style_pdf), _p("费用项目", header_style_pdf),
                  _p("详细说明", header_style_pdf), _p("消费日期", header_style_pdf),
                  _p("金额(元)", header_style_pdf), _p("备注", header_style_pdf),
                  _p("AI建议", header_style_pdf)]
        detail_data = [header]
        for idx, item in enumerate(items, 1):
            detail_data.append([
                _p(str(idx), cell_style_center),
                _p(item["sub_expense_type"]),
                _p(item["description"]),
                _p(item["date"]),
                _p(f"{item['amount']:,.2f}"),
                _p(item["remark"], cell_style_center),
                _p(item["ai_suggestion"]),
            ])
        # 合计行
        total = sum(item['amount'] for item in items)
        detail_data.append(["", "", _p("合计", cell_style_center), "", _p(f"{total:,.2f}"), "", ""])
        
        detail_table = Table(detail_data, colWidths=[30, 60, 90, 65, 55, 40, 120])
        detail_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), CN_FONT),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E8F5E9')),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#FFF3E0')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (4, 0), (4, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(detail_table)
        elements.append(Spacer(1, 15))

    # 附件图片区：发票+凭证图片
    image_paths = []
    try:
        db = SessionLocal()
        db_invoices = db.query(Invoice).filter_by(reimbursement_no=reimbursement_no).all()
        for inv in db_invoices:
            if inv.file_path and os.path.exists(inv.file_path):
                image_paths.append(("发票", inv.file_path))
        db_vouchers = db.query(Voucher).filter_by(reimbursement_no=reimbursement_no).all()
        for v in db_vouchers:
            if v.file_path and os.path.exists(v.file_path):
                image_paths.append(("凭证", v.file_path))
        db.close()
    except Exception:
        pass

    if image_paths:
        elements.append(Paragraph("附件图片", heading_style))
        available_width = A4[0] - 50 * mm
        for label, img_path in image_paths:
            try:
                img = RLImage(img_path)
                img_w, img_h = img.drawWidth, img.drawHeight
                scale = min(available_width / img_w, 200 * mm / img_h, 1.0)
                img.drawWidth = img_w * scale
                img.drawHeight = img_h * scale
                elements.append(Paragraph(f"{label}：{os.path.basename(img_path)}", normal_style))
                elements.append(img)
                elements.append(Spacer(1, 10))
            except Exception:
                elements.append(Paragraph(f"{label}：{os.path.basename(img_path)}（图片加载失败）", normal_style))

    # 审批流程（动态）
    elements.append(Paragraph("审批流程", heading_style))
    approval_style = ParagraphStyle('ApprovalCell', parent=styles['Normal'],
                                     fontSize=11, leading=14, fontName=CN_FONT,
                                     alignment=1, wordWrap='CJK')
    approval_header_style = ParagraphStyle('ApprovalHeader', parent=approval_style,
                                            fontSize=11, leading=14, fontName=CN_FONT,
                                            textColor=colors.black, alignment=1)
    approval_data = [
        [_p("审批环节", approval_header_style), _p("审批人", approval_header_style),
         _p("签字", approval_header_style), _p("日期", approval_header_style)],
    ]
    level_names = {1: "部门审批", 2: "总监审批", 3: "总经理审批"}
    # 从数据库读取审批记录
    try:
        db2 = SessionLocal()
        reimb_record = db2.query(Reimbursements).filter_by(reimbursement_no=reimbursement_no).first()
        if reimb_record:
            approval_records = db2.query(ApprovalRecords).filter_by(
                reimbursement_id=reimb_record.id
            ).order_by(ApprovalRecords.approval_level).all()
            for rec in approval_records:
                level_name = level_names.get(rec.approval_level, f"第{rec.approval_level}级审批")
                approver_name = rec.approver_name or ""
                signature = rec.approver_name if rec.status == "approved" else ""
                date_str = rec.approved_at.strftime('%Y-%m-%d') if rec.status == "approved" and rec.approved_at else ""
                approval_data.append([
                    _p(level_name, approval_style), _p(approver_name, approval_style),
                    _p(signature, approval_style), _p(date_str, approval_style)
                ])
        db2.close()
    except Exception:
        pass
    if len(approval_data) == 1:
        approval_data.append([_p("（待提交审批）", approval_style), "", "", ""])
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
