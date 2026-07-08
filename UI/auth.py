import gradio as gr

from src.db.auth import authenticate_user
from UI.constants import TAB_CHAT
from UI.utils import _render_jump_buttons, _tab_visibility_js
from UI.chat_page import _get_greeting, save_chat_message


def do_login(user_id, password):
    user = authenticate_user(user_id, password)
    if user:
        role_text = {"employee": "员工", "manager": "经理", "admin": "管理员"}[user["role"]]
        info = f"当前用户：**{user['name']}** ({user['user_id']}) | 角色：{role_text} | 部门：{user['department_id'] or '无'}"
        is_manager = user["role"] in ("manager", "admin")

        greeting = _get_greeting(user)
        chat = [{"role": "assistant", "content": _render_jump_buttons(greeting)}]
        save_chat_message(user['user_id'], "assistant", greeting)

        return (
            user, gr.update(visible=False), gr.update(visible=True), info,
            gr.Tabs(selected=TAB_CHAT), _tab_visibility_js(is_manager), chat, user
        )
    return (
        None, gr.update(visible=True), gr.update(visible=False), "工号或密码错误",
        gr.Tabs(selected=TAB_CHAT), _tab_visibility_js(False), [], None
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
        None
    )


def restore_from_storage(stored_user):
    if stored_user and isinstance(stored_user, dict) and stored_user.get('user_id'):
        role_text = {"employee": "员工", "manager": "经理", "admin": "管理员"}[stored_user["role"]]
        info = f"当前用户：**{stored_user['name']}** ({stored_user['user_id']}) | 角色：{role_text} | 部门：{stored_user['department_id'] or '无'}"
        is_manager = stored_user["role"] in ("manager", "admin")

        greeting = _get_greeting(stored_user)
        chat = [{"role": "assistant", "content": _render_jump_buttons(greeting)}]
        save_chat_message(stored_user['user_id'], "assistant", greeting)

        return (
            stored_user, gr.update(visible=False), gr.update(visible=True), info,
            gr.Tabs(selected=TAB_CHAT), _tab_visibility_js(is_manager), chat, stored_user
        )

    return (
        None,
        gr.update(visible=True),
        gr.update(visible=False),
        "",
        gr.Tabs(selected=TAB_CHAT),
        _tab_visibility_js(False),
        [],
        None
    )


def do_register(username, password, name, email, department_id, role):
    if not username or not password or not name:
        return "请填写所有必填项"
    from src.db.auth import register_user
    return register_user(username, password, name, email or "", department_id, role)
