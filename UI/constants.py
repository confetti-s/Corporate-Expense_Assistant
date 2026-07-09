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
.pending,
.generating,
[aria-busy="true"] { border-color: transparent !important; outline: none !important; box-shadow: none !important; }
.chat-input-row { gap: 0 !important; border: 1px solid #ddd; border-radius: 6px; overflow: hidden; align-items: stretch !important; }
.chat-input-field { border: none !important; border-radius: 0 !important; box-shadow: none !important; flex: 1 !important; min-width: 0 !important; }
.chat-input-field textarea { padding-right: 40px !important; }
.voucher-icon-btn, .voucher-icon-btn > div, .voucher-icon-btn button {
    border: none !important;
    border-radius: 0 !important;
    border-left: 1px solid #ddd !important;
    background: transparent !important;
    color: #666 !important;
    min-width: 32px !important;
    max-width: 32px !important;
    width: 32px !important;
    flex: 0 0 32px !important;
    padding: 0 !important;
    margin: 0 !important;
    font-size: 16px !important;
    line-height: 1 !important;
}
.voucher-icon-btn:hover, .voucher-icon-btn:hover button { background: #f5f5f5 !important; color: #333 !important; }
"""
