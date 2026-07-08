import os
import re

from src.db.database import SessionLocal
from src.db.models import ChatHistory
from src.tools.ocr_tool import ocr_invoice, batch_ocr_invoices
from UI.utils import _render_jump_buttons

# ===================== Agent 初始化 =====================

agent_available = False
agent_run = None

try:
    from src.agent.expense_agent import run_agent as _agent_run, test_agent
    agent_run = _agent_run
    agent_available = test_agent()
    print(f"Agent 状态: {'可用' if agent_available else '不可用'}")
except Exception as e:
    print(f"Agent 导入失败: {e}")
    import traceback
    traceback.print_exc()


# ===================== 对话历史持久化 =====================

def save_chat_message(user_id: str, role: str, content: str, reimbursement_id: int = None):
    if not user_id:
        return
    db = SessionLocal()
    try:
        record = ChatHistory(
            user_id=user_id,
            role=role,
            content=content,
            reimbursement_id=reimbursement_id
        )
        db.add(record)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"保存聊天记录失败: {e}")
    finally:
        db.close()


def load_chat_history(user_id: str, limit: int = 10) -> list:
    if not user_id:
        return []
    db = SessionLocal()
    try:
        records = db.query(ChatHistory)\
            .filter_by(user_id=user_id)\
            .order_by(ChatHistory.created_at.desc())\
            .limit(limit)\
            .all()

        history = []
        for record in reversed(records):
            history.append({
                "role": record.role,
                "content": record.content
            })
        return history
    finally:
        db.close()


def send_greeting(chat_history, user_state):
    """登录后流式输出智能体问候"""
    if not user_state:
        yield chat_history or []
        return

    chat_history = chat_history or []

    enhanced_message = "你好"
    if user_state:
        enhanced_message += (
            f"\n[当前用户: {user_state['name']}({user_state['user_id']}), "
            f"部门: {user_state['department_id']}]"
        )

    chat_history.append({"role": "assistant", "content": "请稍等..."})
    yield chat_history

    full_response = ""
    try:
        if agent_available:
            chat_history[-1]["content"] = ""
            for chunk in agent_run(enhanced_message, []):
                if chunk:
                    full_response += chunk
                    display_text = re.sub(r'\[\[.*?\]\]', '', full_response).rstrip()
                    chat_history[-1]["content"] = display_text
                    yield chat_history

            if chat_history and chat_history[-1]["role"] == "assistant":
                rendered = _render_jump_buttons(full_response)
                chat_history[-1]["content"] = rendered
                yield chat_history
        else:
            full_response = "你好！我是企业财务报销助手，有什么可以帮您的吗？"
            chat_history[-1]["content"] = full_response
            yield chat_history
    except Exception as e:
        print(f"send_greeting 错误: {e}")
        full_response = "你好！我是企业财务报销助手，有什么可以帮您的吗？"
        chat_history[-1]["content"] = full_response
        yield chat_history

    if user_state and user_state.get('user_id'):
        save_chat_message(user_state['user_id'], "assistant", full_response)


def load_full_chat_history(user_state):
    """加载用户全部聊天历史，格式化为文本展示"""
    if not user_state:
        return "暂无聊天记录"
    db = SessionLocal()
    try:
        records = db.query(ChatHistory)\
            .filter_by(user_id=user_state['user_id'])\
            .order_by(ChatHistory.id.asc())\
            .all()
        if not records:
            return "暂无聊天记录"
        lines = []
        for r in records:
            role_label = "用户" if r.role == "user" else "助手"
            time_str = r.created_at.strftime('%m-%d %H:%M') if r.created_at else ""
            content = r.content.replace("\\n", "\n") if r.content else ""
            lines.append(f"**{role_label}** ({time_str})\n{content}")
        return "\n\n---\n\n".join(lines)
    finally:
        db.close()


# ===================== 核心对话处理 =====================

def chat_send(message, chat_history, file_uploads, user_state):
    print(f"===== chat_send 被调用 =====")
    print(f"agent_available = {agent_available}")
    print(f"message = {message}")

    if not message or not message.strip():
        yield "", chat_history or []
        return

    chat_history = chat_history or []

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
        chat_history.append({"role": "assistant", "content": f"准备消息失败：{e}"})
        yield "", chat_history
        return

    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": "请稍等..."})
    yield "", chat_history
    print("已显示 '请稍等...'")

    full_response = ""
    try:
        if agent_available:
            print("开始流式执行 Agent...")
            chat_history[-1]["content"] = ""

            for chunk in agent_run(enhanced_message, chat_history[:-1]):
                if chunk:
                    full_response += chunk
                    display_text = re.sub(r'\[\[.*?\]\]', '', full_response).rstrip()
                    chat_history[-1]["content"] = display_text
                    yield "", chat_history

            print(f"流式完成，总长度 {len(full_response)}")

            if chat_history and chat_history[-1]["role"] == "assistant":
                rendered = _render_jump_buttons(full_response)
                chat_history[-1]["content"] = rendered
                yield "", chat_history
        else:
            print("agent_available = False")
            full_response = "抱歉，智能助手暂不可用，请检查API配置。"
            chat_history[-1]["content"] = full_response
            yield "", chat_history

    except Exception as e:
        print(f"chat_send 错误: {e}")
        import traceback
        traceback.print_exc()
        full_response = f"发送消息时出错：{e}"
        chat_history[-1]["content"] = full_response
        yield "", chat_history

    if user_state and user_state.get('user_id'):
        user_id = user_state['user_id']
        save_chat_message(user_id, "user", message)
        if full_response:
            save_chat_message(user_id, "assistant", full_response)
        else:
            save_chat_message(user_id, "assistant", "无回复")
        print(f"对话已保存，用户: {user_id}")


def ocr_file_handler(file, chat_history, user_state):
    if not file:
        return chat_history or [], None

    try:
        files = file if isinstance(file, list) else [file]
        paths = []
        for f in files:
            if f:
                fp = f.name if hasattr(f, 'name') else str(f)
                paths.append(fp)

        user_id = user_state['user_id'] if user_state else ""

        if len(paths) == 0:
            return chat_history or [], None
        elif len(paths) == 1:
            result = ocr_invoice.func(paths[0], uploaded_by=user_id)
            filename = os.path.basename(paths[0])
        else:
            result = batch_ocr_invoices.func(",".join(paths), uploaded_by=user_id)
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
