import gradio as gr

from src.db.auth import authenticate_user
from UI.constants import TAB_CHAT
from UI.utils import _tab_visibility_js

HISTORY_DEFAULT = "点击上方按钮加载历史记录"


def do_login(user_id, password):
    user, error = authenticate_user(user_id, password)
    if user:
        role_text = {"employee": "员工", "manager": "经理", "admin": "管理员"}[user["role"]]
        info = f"当前用户：**{user['name']}** ({user['user_id']}) | 角色：{role_text} | 部门：{user['department_id'] or '无'}"
        is_manager = user["role"] in ("manager", "admin")

        return (

            user, gr.Column(visible=False), gr.Column(visible=True), info,
            gr.Tabs(selected=TAB_CHAT), _tab_visibility_js(is_manager), [], user, "", HISTORY_DEFAULT
        )
    return (
        None, gr.update(visible=True), gr.update(visible=False), error,
        gr.Tabs(selected=TAB_CHAT), _tab_visibility_js(False), [], None, f"❌ {error}", HISTORY_DEFAULT
    )


def do_logout(user_state):
    return (
        None,
        gr.update(visible=True),
        gr.update(visible=False),
        "",
        gr.Tabs(selected=TAB_CHAT),
        _tab_visibility_js(False),
        [],
        None,
        HISTORY_DEFAULT
    )


def restore_from_storage(stored_user):
    if stored_user and isinstance(stored_user, dict) and stored_user.get('user_id'):
        role_text = {"employee": "员工", "manager": "经理", "admin": "管理员"}[stored_user["role"]]
        info = f"当前用户：**{stored_user['name']}** ({stored_user['user_id']}) | 角色：{role_text} | 部门：{stored_user['department_id'] or '无'}"
        is_manager = stored_user["role"] in ("manager", "admin")

        return (

            stored_user, gr.Column(visible=False), gr.Column(visible=True), info,
            gr.Tabs(selected=TAB_CHAT), _tab_visibility_js(is_manager), [], stored_user, HISTORY_DEFAULT
        )

    return (
        None,
        gr.update(visible=True),
        gr.update(visible=False),
        "",
        gr.Tabs(selected=TAB_CHAT),
        _tab_visibility_js(False),
        [],
        None,
        HISTORY_DEFAULT
    )


def do_register(username, password, name, email, department_id, role):
    if not username or not password or not name:
        return "请填写所有必填项"
    from src.db.auth import register_user
    return register_user(username, password, name, email or "", department_id, role)
