import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, ToolMessage
from src.tools import ALL_TOOLS
from prompts import build_system_prompt
from config import DASHSCOPE_API_KEY, WORKSPACE_ID, MODEL_NAME, ALIBABA_MAAS_BASE_URL

# 面向用户的工具：这些工具的返回结果需要展示给用户
USER_FACING_TOOLS = {"查看报销单详情"}
_agent_instance = None

TAB_MAP = {
    "对话报销": "chat",
    "预算看板": "budget",
    "进度查询": "progress",
    "模拟审批": "approval",
}


def get_agent():
    global _agent_instance
    if _agent_instance is None:
        if not DASHSCOPE_API_KEY or not WORKSPACE_ID:
            raise RuntimeError("阿里云百炼API配置未完成，请在.env文件中配置DASHSCOPE_API_KEY和WORKSPACE_ID")

        llm = ChatOpenAI(
            api_key=DASHSCOPE_API_KEY,
            base_url=ALIBABA_MAAS_BASE_URL,
            model=MODEL_NAME,
            temperature=0,
            streaming=True
        )

        system_prompt = build_system_prompt()
        _agent_instance = create_agent(llm, ALL_TOOLS, system_prompt=system_prompt)

    return _agent_instance


def run_agent(user_query: str, chat_history: list = None):
    """生成器函数，逐块返回 Agent 响应（真正的流式输出）"""
    try:
        agent = get_agent()

        messages = []
        if chat_history:
            for turn in chat_history[-10:]:
                if isinstance(turn, dict) and turn.get("role") in ("user", "assistant"):
                    messages.append({"role": turn["role"], "content": turn["content"]})

        messages.append({"role": "user", "content": user_query})

        yielded_any = False

        for event in agent.stream({"messages": messages}, stream_mode="messages"):
            if isinstance(event, tuple) and len(event) >= 2:
                msg = event[0]
                if isinstance(msg, ToolMessage):
                    # 只放行面向用户的工具结果，其余内部工具结果过滤
                    tool_name = getattr(msg, "name", "")
                    if tool_name not in USER_FACING_TOOLS:
                        continue
                if hasattr(msg, "content") and msg.content:
                    content = msg.content
                    # 过滤Agent内部错误信息
                    if content.startswith("Error:") and "is not a valid tool" in content:
                        continue
                    # 在后端也剥离内部标记，防止泄露
                    content = re.sub(r'\[INSTRUCTION:[\s\S]*?\]', '', content)
                    content = re.sub(r'\[NEED_INFO\]', '', content)
                    content = re.sub(r'\n{2,}', '\n', content).strip()
                    if content:
                        yielded_any = True
                        yield content

        if not yielded_any:
            yield "抱歉，我无法理解您的请求，请换一种方式描述。"

    except Exception as e:
        yield f"Agent执行失败：{str(e)}\n请确保已正确配置.env文件中的DASHSCOPE_API_KEY和WORKSPACE_ID"

def parse_jump_links(response_text: str) -> list:
    if not response_text:
        return []
    matches = re.findall(r'\[\[([^\]]+)\]\]', response_text)
    links = []
    for match in matches:
        tab_id = TAB_MAP.get(match.strip())
        if tab_id:
            links.append({"tab_id": tab_id, "label": match.strip()})
    return links


def parse_target_tab(response_text: str) -> str:
    links = parse_jump_links(response_text)
    if links:
        return links[0]["tab_id"]
    return "chat"


def test_agent():
    print("测试Agent...")
    try:
        agent = get_agent()
        print("[OK] Agent创建成功")
        return True
    except Exception as e:
        print(f"[FAIL] Agent创建失败：{e}")
        return False
