from langchain.tools import tool
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.header import Header
import os
from config import SMTP_SERVER, SMTP_PORT, SMTP_USER1, SMTP_PASSWORD1, SMTP_USER2, SMTP_PASSWORD2
from src.db.database import SessionLocal
from src.db.models import Reimbursements, DepartmentApprover, User


@tool("发送邮件")
def send_email(to_email: str, subject: str, body: str, attachment_path: str = None) -> str:
    """
    发送邮件给审批人
    :param to_email: 收件人邮箱地址
    :param subject: 邮件主题
    :param body: 邮件正文内容
    :param attachment_path: 附件文件路径（可选）
    :return: 发送结果字符串
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER2
        msg['To'] = to_email
        msg['Subject'] = Header(subject, 'utf-8')

        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, 'rb') as f:
                part = MIMEApplication(f.read())
            filename = os.path.basename(attachment_path)
            part.add_header('Content-Disposition', 'attachment',
                           filename=('utf-8', '', filename))
            msg.attach(part)

        # SSL vs STARTTLS 自动切换
        if SMTP_PORT == 465:
            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
        else:
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()

        server.login(SMTP_USER2, SMTP_PASSWORD2)
        server.send_message(msg)
        server.quit()

        return f"邮件发送成功！\n收件人：{to_email}\n主题：{subject}\n附件：{attachment_path if attachment_path else '无'}"
    except Exception as e:
        return f"邮件发送失败：{str(e)}\n请检查SMTP配置是否正确。"


@tool("通知审批人")
def notify_approver(reimbursement_no: str, attachment_path: str = None) -> str:
    """
    根据报销单号自动查找第一级审批人的邮箱并发送审批通知邮件，无需手动输入邮箱地址
    :param reimbursement_no: 报销单号，如 RB20260016
    :param attachment_path: 附件文件路径（可选，如报销单PDF）
    :return: 发送结果字符串
    """
    db = SessionLocal()
    try:
        reimb = db.query(Reimbursements).filter_by(reimbursement_no=reimbursement_no).first()
        if not reimb:
            return f"未找到报销单 {reimbursement_no}"

        approver_rec = db.query(DepartmentApprover).filter_by(
            department_id=reimb.department_id,
            approval_level=1
        ).first()
        if not approver_rec:
            return f"部门 {reimb.department_id} 未配置第一级审批人"

        approver_user = db.query(User).filter_by(user_id=approver_rec.approver_id).first()
        if not approver_user or not approver_user.email:
            return f"审批人 {approver_rec.approver_name}（{approver_rec.approver_id}）未设置邮箱"

        ai_suggestion_text = ""
        if reimb.ai_suggestion:
            ai_suggestion_text = f"\n\nAI审核建议：\n{reimb.ai_suggestion}"

        subject = f"【报销审批通知】{reimb.employee_name}-{reimb.expense_type}报销单{reimbursement_no}待审批"
        body = (
            f"您有一条新的报销审批待处理：\n\n"
            f"报销单号：{reimbursement_no}\n"
            f"申请人：{reimb.employee_name}（{reimb.employee_id}）\n"
            f"部门：{reimb.department_id}\n"
            f"费用类型：{reimb.expense_type}\n"
            f"金额：{reimb.total_amount:,.2f} 元\n"
            f"说明：{reimb.description or '无'}\n"
            f"{ai_suggestion_text}\n\n"
            f"请及时登录系统进行审批。"
        )

        result = send_email.func(
            to_email=approver_user.email,
            subject=subject,
            body=body,
            attachment_path=attachment_path,
        )
        return f"已通知第一级审批人 {approver_rec.approver_name}（{approver_rec.approver_id}，邮箱：{approver_user.email}）\n{result}"
    except Exception as e:
        return f"通知审批人失败：{str(e)}"
    finally:
        db.close()
