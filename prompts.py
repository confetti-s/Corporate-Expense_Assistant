from datetime import datetime
from config import SYSTEM_PROMPT_FILE

def load_system_prompt() -> str:
    try:
        with open(SYSTEM_PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "你是一个有用的报销助手，帮助用户处理报销任务。"

def build_system_prompt(extra_vars: dict = None) -> str:
    template = load_system_prompt()
    variables = {
        "当前日期": datetime.now().strftime("%Y年%m月%d日"),
        "当前时间": datetime.now().strftime("%H:%M"),
    }
    if extra_vars:
        variables.update(extra_vars)
    for key, value in variables.items():
        template = template.replace(f"{{{key}}}", str(value))
    return template

def preview_prompt():
    print("=" * 60)
    print("📋 系统提示词预览")
    print("=" * 60)
    print(build_system_prompt())
    print("=" * 60)

if __name__ == "__main__":
    preview_prompt()