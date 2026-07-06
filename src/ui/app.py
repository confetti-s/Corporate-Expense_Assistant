import gradio as gr
import matplotlib.pyplot as plt
import io
from src.tools.budget_tool import get_all_department_budgets, query_department_budget, check_budget_sufficient
from src.tools.progress_tool import query_reimbursement_progress, query_reimbursements_by_date
from src.tools.compliance_tool import compliance_check, calculate_total_amount, get_expense_policy
from src.tools.ocr_tool import ocr_invoice, batch_ocr_invoices
from src.tools.pdf_tool import generate_reimbursement_pdf
from src.tools.email_tool import send_email

try:
    from src.agent.expense_agent import run_agent, test_agent
    agent_available = test_agent()
except Exception as e:
    agent_available = False
    print(f"Agent不可用：{e}")

def chat_with_agent(message, history):
    if agent_available:
        return run_agent(message)
    else:
        return "抱歉，智能助手暂不可用，请检查ARK API配置。您可以使用发票识别、预算看板、进度查询、模拟审批等功能。"

def get_budget_chart():
    import re
    
    budget_info = get_all_department_budgets.func()
    
    dept_names = []
    budget_amounts = []
    spent_amounts = []
    remaining_amounts = []
    
    for line in budget_info.split('\n'):
        if '部门名称' in line:
            match = re.search(r'部门名称：(.+?)\s*\(', line)
            if match:
                dept_names.append(match.group(1).strip())
        elif '总预算' in line:
            match = re.search(r'总预算：([\d,]+(\.\d+)?)\s*元', line)
            if match:
                budget_amounts.append(float(match.group(1).replace(',', '')))
        elif '已使用' in line:
            match = re.search(r'已使用：([\d,]+(\.\d+)?)\s*元', line)
            if match:
                spent_amounts.append(float(match.group(1).replace(',', '')))
        elif '剩余预算' in line:
            match = re.search(r'剩余预算：([\d,]+(\.\d+)?)\s*元', line)
            if match:
                remaining_amounts.append(float(match.group(1).replace(',', '')))
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    
    bars1 = ax1.bar(dept_names, budget_amounts, label='总预算', color='#4CAF50')
    bars2 = ax1.bar(dept_names, spent_amounts, label='已使用', color='#FF9800')
    ax1.set_xlabel('部门')
    ax1.set_ylabel('金额（元）')
    ax1.set_title('部门预算使用情况')
    ax1.legend()
    ax1.ticklabel_format(axis='y', style='plain')
    
    ax2.pie(remaining_amounts, labels=dept_names, autopct='%1.1f%%', colors=['#4CAF50', '#8BC34A', '#CDDC39', '#FFC107', '#FF5722'])
    ax2.set_title('剩余预算占比')
    
    plt.tight_layout()
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    
    return buf

def query_progress_ui(reimbursement_no):
    if not reimbursement_no:
        return "请输入报销单号"
    return query_reimbursement_progress.func(reimbursement_no)

with gr.Blocks(title="企业财务报销助手") as demo:
    gr.Markdown("# 企业财务报销助手")
    
    with gr.Tab("对话报销"):
        gr.ChatInterface(chat_with_agent)
        if not agent_available:
            gr.Markdown("⚠️ 智能助手暂不可用，请检查.env文件中的ARK API配置")
    
    with gr.Tab("预算看板"):
        with gr.Row():
            chart_output = gr.Image(label="预算图表", height=300)
        budget_text = gr.Textbox(label="预算详情", lines=10, interactive=False)
        
        def update_budget():
            return get_budget_chart(), get_all_department_budgets.func()
        
        gr.Button("刷新数据").click(fn=update_budget, outputs=[chart_output, budget_text])
    
    with gr.Tab("进度查询"):
        reimbursement_no_input = gr.Textbox(label="报销单号", placeholder="例如：RB20260001")
        progress_output = gr.Textbox(label="审批进度", lines=15, interactive=False)
        gr.Button("查询").click(fn=query_progress_ui, inputs=[reimbursement_no_input], outputs=[progress_output])
    
    with gr.Tab("模拟审批"):
        gr.Markdown("## 模拟审批页面")
        gr.Markdown("审批人可以在此页面处理报销申请")
        
        pending_list = gr.Textbox(label="待审批列表", lines=10, interactive=False)
        
        def load_pending():
            from src.db.database import SessionLocal
            from src.db.models import Reimbursements
            db = SessionLocal()
            try:
                pending = db.query(Reimbursements).filter(Reimbursements.status == "pending").all()
                result = "待审批报销单列表：\n\n"
                for p in pending:
                    result += f"报销单号：{p.reimbursement_no}\n员工：{p.employee_name}\n金额：{p.total_amount:,.2f}元\n费用类型：{p.expense_type}\n提交时间：{p.created_at.strftime('%Y-%m-%d %H:%M')}\n------------------------\n"
                return result if pending else "暂无待审批报销单"
            finally:
                db.close()
        
        gr.Button("加载待审批列表").click(fn=load_pending, outputs=pending_list)
        
        with gr.Row():
            approve_no = gr.Textbox(label="报销单号")
            action = gr.Radio(choices=["通过", "驳回"], label="审批操作")
            comment = gr.Textbox(label="审批意见")
        
        def approve_action(no, act, com):
            from src.db.database import SessionLocal
            from src.db.models import Reimbursements, ApprovalRecords
            from datetime import datetime
            
            db = SessionLocal()
            try:
                reimbursement = db.query(Reimbursements).filter_by(reimbursement_no=no).first()
                if not reimbursement:
                    return f"未找到报销单号 {no}"
                
                status_map = {"通过": "approved", "驳回": "rejected"}
                
                new_record = ApprovalRecords(
                    reimbursement_id=reimbursement.id,
                    approver_id="A001",
                    approver_name="审批人",
                    approval_level=1,
                    status=status_map[act],
                    comment=com or ("同意" if act == "通过" else "驳回"),
                    approved_at=datetime.now()
                )
                db.add(new_record)
                
                reimbursement.status = status_map[act]
                reimbursement.updated_at = datetime.now()
                db.commit()
                
                return f"报销单 {no} 已{act}，审批意见：{com or '无'}"
            finally:
                db.close()
        
        gr.Button("提交审批").click(fn=approve_action, inputs=[approve_no, action, comment], outputs=pending_list)

if __name__ == "__main__":
    demo.launch()