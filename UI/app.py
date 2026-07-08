import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gradio as gr

from src.db.database import init_db
from src.db.seed_data import main as seed_main

init_db()
seed_main()

from UI.constants import CUSTOM_CSS, TAB_CHAT, TAB_BUDGET, TAB_PROGRESS, TAB_APPROVAL
from UI.chat_page import (
    agent_available, chat_send, ocr_file_handler, clear_chat,
    load_full_chat_history, send_greeting
)
from UI.budget_page import update_budget
from UI.progress_page import (
    load_my_reimbursements, on_reimb_select, query_progress_ui, query_by_date_range,
    auto_load_on_tab_change
)
from UI.approval_page import (
    load_pending_for_approver, on_pending_select, do_approve
)
from UI.auth import do_login, do_logout, restore_from_storage, do_register

# ===================== UI 定义 =====================

with gr.Blocks(title="企业财务报销助手") as demo:
    user_state = gr.State(None)

    user_storage = gr.BrowserState(
        storage_key="expense_user_data",
    )

    # ========== 登录区域 ==========
    with gr.Column(visible=False, elem_classes=["login-area"]) as login_area:
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
            reg_email = gr.Textbox(label="邮箱", placeholder="如 zhangsan@example.com")
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
    with gr.Column(visible=True) as main_area:
        user_info_bar = gr.Markdown("", elem_classes=["user-bar"])
        logout_btn = gr.Button("退出登录", size="sm")
        tab_js_injector = gr.HTML(elem_classes=["tab-js-injector"])

        with gr.Tabs(selected=TAB_CHAT) as tabs_container:

            # ========== Tab 1: 对话报销 ==========
            with gr.Tab(label="对话报销", id=TAB_CHAT):
                with gr.Row():
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

                        if not agent_available:
                            gr.Markdown("**注意:** 智能助手暂不可用")

                        gr.Markdown("**快捷示例:**")
                        gr.Examples(
                            examples=[
                                "我要报销一笔差旅费",
                                "查一下报销单RB20260001的进度",
                            ],
                            inputs=[gr.Textbox(visible=False)],
                        )

                    with gr.Column(scale=2):
                        chatbot_display = gr.Chatbot(
                            height=450,
                            label="报销助手对话",
                            sanitize_html=False
                        )
                        with gr.Row():
                            msg_input = gr.Textbox(
                                placeholder="描述您的报销需求...",
                                show_label=False,
                                scale=4
                            )
                            send_btn = gr.Button("发送", variant="primary", scale=1)

                        with gr.Accordion("查看历史聊天", open=False):
                            history_refresh_btn = gr.Button("刷新历史记录", size="sm")
                            history_display = gr.Markdown("点击上方按钮加载历史记录", height=300)

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
                    inputs=[file_input, chatbot_display, user_state],
                    outputs=[chatbot_display, file_input]
                )
                clear_btn.click(
                    fn=clear_chat,
                    outputs=[chatbot_display, msg_input]
                )
                jump_progress_btn.click(fn=lambda: gr.Tabs(selected=TAB_PROGRESS), outputs=tabs_container)
                history_refresh_btn.click(fn=load_full_chat_history, inputs=user_state, outputs=history_display)

            # ========== Tab 2: 预算看板 ==========
            with gr.Tab(label="预算看板", id=TAB_BUDGET) as budget_tab:
                chart_output = gr.Image(label="预算可视化图表", height=350)
                budget_text = gr.Textbox(label="各部门预算详情", lines=12, interactive=False)

                with gr.Row():
                    refresh_budget_btn = gr.Button("刷新数据", variant="primary")
                    jump_chat_from_budget = gr.Button("发起新报销 -->")

                refresh_budget_btn.click(fn=update_budget, outputs=[chart_output, budget_text])
                jump_chat_from_budget.click(fn=lambda: gr.Tabs(selected=TAB_CHAT), outputs=tabs_container)

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

                my_reimb_df.select(fn=on_reimb_select, inputs=user_state, outputs=progress_detail)
                refresh_my_btn.click(fn=load_my_reimbursements, inputs=user_state, outputs=my_reimb_df)
                query_single_btn.click(fn=query_progress_ui, inputs=reimbursement_no_input, outputs=progress_detail)
                query_range_btn.click(fn=query_by_date_range, inputs=[date_start, date_end, user_state], outputs=progress_detail)

            # ========== Tab 4: 模拟审批 ==========
            with gr.Tab(label="模拟审批", id=TAB_APPROVAL) as approval_tab:
                gr.Markdown("## 我的审批列表")

                pending_df = gr.Dataframe(
                    headers=["报销单号", "申请人", "部门", "金额(元)", "费用类型", "审批级别", "审批状态"],
                    datatype=["str", "str", "str", "str", "str", "str", "str"],
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

                pending_df.select(fn=on_pending_select, outputs=[selected_no_display, approval_chain])
                refresh_pending_btn.click(fn=load_pending_for_approver, inputs=user_state, outputs=pending_df)
                submit_approve_btn.click(
                    fn=do_approve,
                    inputs=[selected_no_display, action_radio, comment_input, user_state],
                    outputs=[approve_result, pending_df, selected_no_display]
                )
                jump_progress_from_approval.click(fn=lambda: gr.Tabs(selected=TAB_PROGRESS), outputs=tabs_container)
                jump_chat_from_approval.click(fn=lambda: gr.Tabs(selected=TAB_CHAT), outputs=tabs_container)

    # ========== Tab 切换时自动刷新 ==========
    tabs_container.change(fn=update_budget, outputs=[chart_output, budget_text])
    tabs_container.change(fn=auto_load_on_tab_change, inputs=user_state, outputs=my_reimb_df)
    tabs_container.change(fn=load_pending_for_approver, inputs=user_state, outputs=pending_df)

    # ========== 登录/注册事件 ==========
    login_btn.click(
        fn=do_login,
        inputs=[login_username, login_password],
        outputs=[user_state, login_area, main_area, user_info_bar, tabs_container, tab_js_injector, chatbot_display, user_storage]
    ).then(
        fn=send_greeting,
        inputs=[chatbot_display, user_state],
        outputs=[chatbot_display]
    )
    login_password.submit(
        fn=do_login,
        inputs=[login_username, login_password],
        outputs=[user_state, login_area, main_area, user_info_bar, tabs_container, tab_js_injector, chatbot_display, user_storage]
    ).then(
        fn=send_greeting,
        inputs=[chatbot_display, user_state],
        outputs=[chatbot_display]
    )
    logout_btn.click(
        fn=do_logout,
        inputs=user_state,
        outputs=[user_state, login_area, main_area, user_info_bar, tabs_container, tab_js_injector, chatbot_display, user_storage],
        js="""
        () => {
            try {
                localStorage.removeItem('expense_user_data');
                console.log('localStorage 已清除');
            } catch(e) {}
            setTimeout(() => {
                document.querySelectorAll('.login-area').forEach(el => { if(el) el.style.display = 'block'; });
                document.querySelectorAll('.main').forEach(el => { if(el) el.style.display = 'none'; });
            }, 100);
        }
        """
    )
    reg_btn.click(fn=do_register, inputs=[reg_username, reg_password, reg_name, reg_email, reg_dept, reg_role], outputs=reg_msg)

    # ========== 页面加载时从 BrowserState 恢复登录 ==========
    demo.load(
        fn=restore_from_storage,
        inputs=[user_storage],
        outputs=[
            user_state,
            login_area,
            main_area,
            user_info_bar,
            tabs_container,
            tab_js_injector,
            chatbot_display,
            user_storage
        ]
    ).then(
        fn=send_greeting,
        inputs=[chatbot_display, user_state],
        outputs=[chatbot_display]
    )
