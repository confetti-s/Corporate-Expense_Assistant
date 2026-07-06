import os
import sys
import re
import tempfile
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gradio as gr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

from src.db.database import init_db, SessionLocal
from src.db.models import Reimbursements, ApprovalRecords, DepartmentBudget, User, DepartmentApprover
from src.db.seed_data import main as seed_main
from src.db.auth import authenticate_user, hash_password

# 初始化数据库
init_db()
seed_main()

from src.tools.budget_tool import get_all_department_budgets, query_department_budget, check_budget_sufficient
from src.tools.progress_tool import query_reimbursement_progress, query_reimbursements_by_date
from src.tools.compliance_tool import compliance_check, calculate_total_amount, get_expense_policy
from src.tools.ocr_tool import ocr_invoice, batch_ocr_invoices
from src.tools.pdf_tool import generate_reimbursement_pdf
from src.tools.email_tool import send_email
from src.tools.reimbursement_tool import create_reimbursement, submit_for_approval
from src.tools.approval_tool import approve_or_reject_reimbursement

agent_available = False
try:
    from src.agent.expense_agent import run_agent as agent_run, test_agent
    agent_available = test_agent()
    print(f"✅ Agent 状态: {'可用' if agent_available else '不可用'}")
except Exception as e:
    print(f"❌ Agent 导入失败: {e}")
    import traceback
    traceback.print_exc()
    agent_available = False

TAB_CHAT = "chat"
TAB_BUDGET = "budget"
TAB_PROGRESS = "progress"
TAB_APPROVAL = "approval"

STATUS_MAP = {"pending": "待审批", "reviewing": "审批中", "approved": "已通过", "rejected": "已驳回", "draft": "草稿"}

CUSTOM_CSS = """
.login-area { max-width: 420px; margin: 80px auto; padding: 30px; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,0.1); background: #fff; }
.user-bar { background: linear-gradient(90deg, #e3f2fd, #f3e5f5); padding: 10px 20px; border-radius: 8px; margin-bottom: 12px; }
.user-bar span { font-size: 15px; }
.tab-nav button { font-size: 14px !important; }
"""


# ===================== 认证 =====================

def do_login(username, password):
    user = authenticate_user(username, password)
    if user:
        role_text = {"employee": "员工", "manager": "经理", "admin": "管理员"}[user["role"]]
        info = f"当前用户：**{user['name']}** ({user['user_id']}) | 角色：{role_text} | 部门：{user['department_id'] or '无'}"
        is_manager = user["role"] in ("manager", "admin")
        return (
            user,
            gr.Column(visible=False),
            gr.Column(visible=True),
            info,
            gr.Tab(visible=is_manager),
            gr.Tab(visible=is_manager),
        )
    return (
        None,
        gr.Column(visible=True),
        gr.Column(visible=False),
        "用户名或密码错误",
        gr.Tab(visible=False),
        gr.Tab(visible=False),
    )


def do_logout(user_state):
    return (
        None,
        gr.Column(visible=True),
        gr.Column(visible=False),
        "",
        gr.Tab(visible=False),
        gr.Tab(visible=False),
    )


# ===================== 对话报销 =====================

def chat_send(message, chat_history, file_uploads, user_state):
    """
    流式输出：
    1. 用户消息立即显示
    2. AI显示"正在思考..."
    3. Agent逐块流式输出
    """

    print(f"🔍 ===== chat_send 被调用 =====")
    print(f"🔍 agent_available = {agent_available}")
    print(f"🔍 message = {message}")

    if not message or not message.strip():
        yield "", chat_history or []
        return

    chat_history = chat_history or []

    # ========= 构造增强消息（发送给Agent）=========
    enhanced_message = message

    try:
        if file_uploads:
            files = file_uploads if isinstance(file_uploads, list) else [file_uploads]

            file_info = []

            for f in files:
                if f:
                    fp = f.name if hasattr(f, "name") else str(f)
                    file_info.append(f"[附件: {os.path.basename(fp)}]")

            if file_info:
                enhanced_message += "\n\n" + "\n".join(file_info)

        if user_state:
            enhanced_message += (
                f"\n[当前用户: {user_state['name']}({user_state['user_id']}), "
                f"部门: {user_state['department_id']}]"
            )

    except Exception as e:
        chat_history.append(
            {
                "role": "assistant",
                "content": f"准备消息失败：{e}"
            }
        )
        yield "", chat_history
        return

    # ========= 第一步：立即显示用户消息 =========
    chat_history.append(
        {
            "role": "user",
            "content": message
        }
    )

    # ========= 第二步：显示"请稍等..." =========
    chat_history.append(
        {
            "role": "assistant",
            "content": "请稍等..."
        }
    )

    # 立即刷新界面，显示用户消息和"请稍等..."
    yield "", chat_history
    print("✅ 已显示 '请稍等...'")

    # ========= 第三步：流式执行Agent =========
    try:
        if agent_available:
            print("🚀 开始流式执行 Agent...")
            full_response = ""
            chat_history[-1]["content"] = ""
            
            chunk_count = 0
            for chunk in agent_run(enhanced_message, chat_history[:-1]):
                chunk_count += 1
                #print(f"📦 收到第 {chunk_count} 个 chunk: {chunk[:50] if chunk else '空'}...")
                if chunk:
                    full_response += chunk
                    chat_history[-1]["content"] = full_response
                    yield "", chat_history
            
            print(f"✅ 流式完成，共 {chunk_count} 个 chunks，总长度 {len(full_response)}")
        else:
            print("⚠️ agent_available = False")
            response = "抱歉，智能助手暂不可用，请检查API配置。"
            chat_history[-1]["content"] = response
            yield "", chat_history

    except Exception as e:
        print(f"❌ chat_send 错误: {e}")
        import traceback
        traceback.print_exc()
        chat_history[-1]["content"] = f"发送消息时出错：{e}"
        yield "", chat_history


def ocr_file_handler(file, chat_history):
    if not file:
        return chat_history or [], None

    try:
        files = file if isinstance(file, list) else [file]
        paths = []
        for f in files:
            if f:
                fp = f.name if hasattr(f, 'name') else str(f)
                paths.append(fp)

        if len(paths) == 0:
            return chat_history or [], None
        elif len(paths) == 1:
            result = ocr_invoice.func(paths[0])
            filename = os.path.basename(paths[0])
        else:
            result = batch_ocr_invoices.func(",".join(paths))
            filename = f"{len(paths)}个文件"
    except Exception as e:
        filename = "文件"
        result = f"识别发票时出错：{str(e)}"

    chat_history = chat_history or []
    chat_history.append({"role": "user", "content": f"[上传发票] {filename}"})
    chat_history.append({"role": "assistant", "content": result})

    return chat_history, None


def clear_chat():
    return [], ""


# ===================== 预算看板 =====================

def get_budget_chart():
    try:
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

        if not dept_names:
            return None

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

        x = range(len(dept_names))
        ax1.bar(x, budget_amounts, label='总预算', color='#4CAF50', alpha=0.7)
        ax1.bar(x, spent_amounts, label='已使用', color='#FF9800')
        ax1.set_xticks(x)
        ax1.set_xticklabels(dept_names, fontsize=9)
        ax1.set_ylabel('金额（元）')
        ax1.set_title('部门预算使用情况')
        ax1.legend()
        ax1.ticklabel_format(axis='y', style='plain')

        colors = ['#4CAF50', '#8BC34A', '#CDDC39', '#FFC107', '#FF5722']
        ax2.pie(remaining_amounts, labels=dept_names, autopct='%1.1f%%',
                colors=colors[:len(dept_names)])
        ax2.set_title('剩余预算占比')

        plt.tight_layout()
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        plt.savefig(tmp.name, format='png', dpi=100)
        plt.close()
        return tmp.name
    except Exception as e:
        print(f"预算图表生成错误: {e}")
        return None


def update_budget():
    return get_budget_chart(), get_all_department_budgets.func()


# ===================== 进度查询 =====================

def load_my_reimbursements(user_state):
    if not user_state:
        return pd.DataFrame(columns=["报销单号", "费用类型", "金额(元)", "状态", "创建日期"])

    db = SessionLocal()
    try:
        records = db.query(Reimbursements).filter_by(
            employee_id=user_state['user_id']
        ).order_by(Reimbursements.created_at.desc()).all()

        data = []
        for r in records:
            data.append([
                r.reimbursement_no,
                r.expense_type,
                f"{r.total_amount:,.2f}",
                STATUS_MAP.get(r.status, r.status),
                r.created_at.strftime('%Y-%m-%d'),
            ])

        return pd.DataFrame(data, columns=["报销单号", "费用类型", "金额(元)", "状态", "创建日期"])
    finally:
        db.close()


def on_reimb_select(evt: gr.SelectData, user_state):
    if not evt.value:
        return ""
    # evt.value 是单元格的值，需要提取报销单号
    # 从选中的行获取报销单号
    try:
        selected_value = str(evt.value)
        # 尝试匹配报销单号格式 RB20XXXXXX
        match = re.match(r'RB\d{8}', selected_value)
        if match:
            return query_reimbursement_progress.func(match.group())
    except Exception:
        pass
    return ""


def query_progress_ui(reimbursement_no):
    if not reimbursement_no:
        return "请输入报销单号"
    return query_reimbursement_progress.func(reimbursement_no)


def query_by_date_range(start_date, end_date, user_state):
    if not start_date or not end_date:
        return "请输入开始和结束日期（格式：YYYY-MM-DD）"
    emp_id = user_state['user_id'] if user_state else None
    return query_reimbursements_by_date.func(start_date, end_date, emp_id)


# ===================== 模拟审批 =====================

def load_pending_for_approver(user_state):
    if not user_state or user_state['role'] not in ('manager', 'admin'):
        return pd.DataFrame(columns=["报销单号", "申请人", "部门", "金额(元)", "费用类型", "审批级别"])

    db = SessionLocal()
    try:
        pending_approvals = db.query(ApprovalRecords).filter_by(
            approver_id=user_state['user_id'],
            status="pending"
        ).all()

        data = []
        for rec in pending_approvals:
            reimb = db.query(Reimbursements).filter_by(id=rec.reimbursement_id).first()
            if reimb and reimb.status in ("pending", "reviewing"):
                # 校验前置级别是否已通过
                if rec.approval_level > 1:
                    prev_ok = all(
                        db.query(ApprovalRecords).filter_by(
                            reimbursement_id=reimb.id,
                            approval_level=pl
                        ).first().status == "approved"
                        for pl in range(1, rec.approval_level)
                        if db.query(ApprovalRecords).filter_by(
                            reimbursement_id=reimb.id,
                            approval_level=pl
                        ).first()
                    )
                    if not prev_ok:
                        continue

                dept_name = reimb.department_id
                dept = db.query(DepartmentBudget).filter_by(department_id=reimb.department_id).first()
                if dept:
                    dept_name = dept.department_name

                data.append([
                    reimb.reimbursement_no,
                    reimb.employee_name,
                    dept_name,
                    f"{reimb.total_amount:,.2f}",
                    reimb.expense_type,
                    f"L{rec.approval_level}",
                ])

        return pd.DataFrame(data, columns=["报销单号", "申请人", "部门", "金额(元)", "费用类型", "审批级别"])
    finally:
        db.close()


def on_pending_select(evt: gr.SelectData):
    if not evt.value:
        return "", ""
    selected_value = str(evt.value)
    match = re.match(r'RB\d{8}', selected_value)
    if match:
        no = match.group()
        detail = query_reimbursement_progress.func(no)
        return no, detail
    return "", ""


def do_approve(selected_no, action, comment, user_state):
    if not user_state or not selected_no:
        return "请先选择一条报销单", pd.DataFrame(), ""
    action_key = "approve" if action == "通过" else "reject"
    result = approve_or_reject_reimbursement.func(selected_no, action_key, user_state['user_id'], comment or "")
    new_df = load_pending_for_approver(user_state)
    return result, new_df, ""


# ===================== 注册 =====================

def do_register(username, password, name, department_id, role):
    if not username or not password or not name:
        return "请填写所有必填项"
    from src.db.auth import register_user
    return register_user(username, password, name, "", department_id, role)


# ===================== UI 定义 =====================

with gr.Blocks(title="企业财务报销助手") as demo:
    user_state = gr.State(None)

    # ========== 登录区域 ==========
    with gr.Column(visible=True, elem_classes=["login-area"]) as login_area:
        gr.Markdown("# 企业财务报销助手")
        gr.Markdown("请登录以使用系统")
        login_username = gr.Textbox(label="用户名", placeholder="如 zhangsan / sunjl / admin")
        login_password = gr.Textbox(label="密码", type="password", placeholder="默认密码: 123456")
        with gr.Row():
            login_btn = gr.Button("登录", variant="primary", scale=2)
        login_msg = gr.Markdown("")

        with gr.Accordion("注册新用户", open=False):
            reg_username = gr.Textbox(label="用户名")
            reg_password = gr.Textbox(label="密码", type="password")
            reg_name = gr.Textbox(label="姓名")
            reg_dept = gr.Dropdown(
                label="部门",
                choices=["D001", "D002", "D003", "D004", "D005"],
                value="D001"
            )
            reg_role = gr.Dropdown(
                label="角色",
                choices=[("员工", "employee"), ("经理", "manager")],
                value="employee",
            )
            reg_btn = gr.Button("注册", variant="secondary")
            reg_msg = gr.Markdown("")

    # ========== 主功能区域 ==========
    with gr.Column(visible=False) as main_area:
        user_info_bar = gr.Markdown("", elem_classes=["user-bar"])
        logout_btn = gr.Button("退出登录", size="sm")

        with gr.Tabs(selected=TAB_CHAT) as tabs_container:

            # ========== Tab 1: 对话报销 ==========
            with gr.Tab(label="对话报销", id=TAB_CHAT):
                with gr.Row():
                    # 左列：文件上传 + 操作
                    with gr.Column(scale=1):
                        gr.Markdown("### 票据上传")
                        file_input = gr.File(
                            label="上传发票文件",
                            file_types=[".jpg", ".jpeg", ".png", ".bmp", ".pdf"],
                            file_count="multiple"
                        )
                        ocr_btn = gr.Button("识别发票", variant="secondary")
                        clear_btn = gr.Button("清空对话", variant="secondary")

                        gr.Markdown("---")
                        gr.Markdown("### 快捷跳转")
                        jump_progress_btn = gr.Button("查进度 >>", size="sm")
                        jump_budget_btn = gr.Button("看预算 >>", size="sm")

                        if not agent_available:
                            gr.Markdown("**注意:** 智能助手暂不可用")

                        gr.Markdown("**快捷示例:**")
                        gr.Examples(
                            examples=[
                                "我要报销一笔差旅费",
                                "查一下报销单RB20260001的进度",
                                "看看技术部的预算还剩多少",
                            ],
                            inputs=[gr.Textbox(visible=False)],
                        )

                    # 右列：对话区
                    with gr.Column(scale=2):
                        chatbot_display = gr.Chatbot(
                            
                            height=450, 
                            label="报销助手对话"
                            )
                        with gr.Row():
                            msg_input = gr.Textbox(
                                placeholder="描述您的报销需求...",
                                show_label=False,
                                scale=4
                            )
                            send_btn = gr.Button("发送", variant="primary", scale=1)

                send_btn.click(
                    fn=chat_send,
                    inputs=[msg_input, chatbot_display, file_input, user_state],
                    outputs=[msg_input, chatbot_display]
                )
                msg_input.submit(
                    fn=chat_send,
                    inputs=[msg_input, chatbot_display, file_input, user_state],
                    outputs=[msg_input, chatbot_display]
                )
                ocr_btn.click(
                    fn=ocr_file_handler,
                    inputs=[file_input, chatbot_display],
                    outputs=[chatbot_display, file_input]
                )
                clear_btn.click(
                    fn=clear_chat,
                    outputs=[chatbot_display, msg_input]
                )
                jump_progress_btn.click(fn=lambda: gr.Tabs(selected=TAB_PROGRESS), outputs=tabs_container)
                jump_budget_btn.click(fn=lambda: gr.Tabs(selected=TAB_BUDGET), outputs=tabs_container)

            # ========== Tab 2: 预算看板 ==========
            with gr.Tab(label="预算看板", id=TAB_BUDGET) as budget_tab:
                chart_output = gr.Image(label="预算可视化图表", height=350)
                budget_text = gr.Textbox(label="各部门预算详情", lines=12, interactive=False)

                with gr.Row():
                    refresh_budget_btn = gr.Button("刷新数据", variant="primary")
                    jump_chat_from_budget = gr.Button("发起新报销 -->")

                refresh_budget_btn.click(fn=update_budget, outputs=[chart_output, budget_text])
                jump_chat_from_budget.click(fn=lambda: gr.Tabs(selected=TAB_CHAT), outputs=tabs_container)

                demo.load(fn=update_budget, outputs=[chart_output, budget_text])

            # ========== Tab 3: 进度查询 ==========
            with gr.Tab(label="进度查询", id=TAB_PROGRESS):
                gr.Markdown("## 我的报销记录")

                my_reimb_df = gr.Dataframe(
                    headers=["报销单号", "费用类型", "金额(元)", "状态", "创建日期"],
                    datatype=["str", "str", "str", "str", "str"],
                    interactive=False,
                    max_height=280,
                    label="点击行查看详情",
                )
                refresh_my_btn = gr.Button("刷新列表", variant="secondary")

                gr.Markdown("---")

                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("**按单号查询**")
                        reimbursement_no_input = gr.Textbox(label="报销单号", placeholder="RB20260001")
                        query_single_btn = gr.Button("查询单号", variant="primary")
                    with gr.Column(scale=1):
                        gr.Markdown("**按日期查询**")
                        with gr.Row():
                            date_start = gr.Textbox(label="开始", placeholder="YYYY-MM-DD")
                            date_end = gr.Textbox(label="结束", placeholder="YYYY-MM-DD")
                        query_range_btn = gr.Button("查询", variant="secondary")

                progress_detail = gr.Textbox(label="报销详情 / 审批链路", lines=12, interactive=False)

                with gr.Row():
                    jump_approval_from_progress = gr.Button("去审批 >>")
                    jump_budget_from_progress = gr.Button("查预算 >>")

                # 事件绑定
                my_reimb_df.select(fn=on_reimb_select, inputs=user_state, outputs=progress_detail)
                refresh_my_btn.click(fn=load_my_reimbursements, inputs=user_state, outputs=my_reimb_df)
                query_single_btn.click(fn=query_progress_ui, inputs=reimbursement_no_input, outputs=progress_detail)
                query_range_btn.click(fn=query_by_date_range, inputs=[date_start, date_end, user_state], outputs=progress_detail)
                jump_approval_from_progress.click(fn=lambda: gr.Tabs(selected=TAB_APPROVAL), outputs=tabs_container)
                jump_budget_from_progress.click(fn=lambda: gr.Tabs(selected=TAB_BUDGET), outputs=tabs_container)

                demo.load(fn=load_my_reimbursements, inputs=user_state, outputs=my_reimb_df)

            # ========== Tab 4: 模拟审批 ==========
            with gr.Tab(label="模拟审批", id=TAB_APPROVAL) as approval_tab:
                gr.Markdown("## 我的待审批列表")

                pending_df = gr.Dataframe(
                    headers=["报销单号", "申请人", "部门", "金额(元)", "费用类型", "审批级别"],
                    datatype=["str", "str", "str", "str", "str", "str"],
                    interactive=False,
                    max_height=280,
                    label="点击行选中报销单",
                )
                refresh_pending_btn = gr.Button("刷新列表", variant="primary")

                gr.Markdown("---")
                gr.Markdown("### 审批操作")

                selected_no_display = gr.Textbox(label="选中的报销单号", interactive=False)
                approval_chain = gr.Textbox(label="审批链路详情", lines=6, interactive=False)

                with gr.Row():
                    action_radio = gr.Radio(choices=["通过", "驳回"], value="通过", label="审批操作")
                    comment_input = gr.Textbox(label="审批意见", placeholder="选填...", scale=2)

                submit_approve_btn = gr.Button("提交审批", variant="primary")
                approve_result = gr.Textbox(label="审批结果", lines=3, interactive=False)

                with gr.Row():
                    jump_progress_from_approval = gr.Button("查进度 >>")
                    jump_chat_from_approval = gr.Button("新建报销 >>")

                # 事件绑定
                pending_df.select(fn=on_pending_select, outputs=[selected_no_display, approval_chain])
                refresh_pending_btn.click(fn=load_pending_for_approver, inputs=user_state, outputs=pending_df)
                submit_approve_btn.click(
                    fn=do_approve,
                    inputs=[selected_no_display, action_radio, comment_input, user_state],
                    outputs=[approve_result, pending_df, selected_no_display]
                )
                jump_progress_from_approval.click(fn=lambda: gr.Tabs(selected=TAB_PROGRESS), outputs=tabs_container)
                jump_chat_from_approval.click(fn=lambda: gr.Tabs(selected=TAB_CHAT), outputs=tabs_container)

                demo.load(fn=load_pending_for_approver, inputs=user_state, outputs=pending_df)

    # ========== 登录/注册事件 ==========
    login_btn.click(
        fn=do_login,
        inputs=[login_username, login_password],
        outputs=[user_state, login_area, main_area, user_info_bar, budget_tab, approval_tab]
    )
    login_password.submit(
        fn=do_login,
        inputs=[login_username, login_password],
        outputs=[user_state, login_area, main_area, user_info_bar, budget_tab, approval_tab]
    )
    logout_btn.click(
        fn=do_logout,
        inputs=user_state,
        outputs=[user_state, login_area, main_area, user_info_bar, budget_tab, approval_tab]
    )
    reg_btn.click(fn=do_register, inputs=[reg_username, reg_password, reg_name, reg_dept, reg_role], outputs=reg_msg)


if __name__ == "__main__":
    print("启动企业财务报销助手 v3.0...")
    demo.launch(server_name="127.0.0.1", server_port=7860, css=CUSTOM_CSS)
