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
.tab-js-injector { height: 0; overflow: hidden; margin: 0; padding: 0; }
"""
