import os
from dotenv import load_dotenv

load_dotenv()

DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
WORKSPACE_ID = os.getenv("WORKSPACE_ID")
MODEL_NAME = os.getenv("MODEL_NAME", "deepseek-v4-flash")

BAIDU_OCR_API_KEY = os.getenv("BAIDU_OCR_API_KEY")
BAIDU_OCR_SECRET_KEY = os.getenv("BAIDU_OCR_SECRET_KEY")

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER1 = os.getenv("SMTP_USER1")
SMTP_PASSWORD1 = os.getenv("SMTP_PASSWORD1")
SMTP_USER2 = os.getenv("SMTP_USER2")
SMTP_PASSWORD2 = os.getenv("SMTP_PASSWORD2")
EMAIL_NOTIFICATION_ENABLED = os.getenv("EMAIL_NOTIFICATION_ENABLED", "false").lower() == "true"

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/expense.db")

WORK_ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(WORK_ROOT, "data")
OUTPUTS_DIR = os.path.join(WORK_ROOT, "outputs")

for dir_path in [DATA_DIR, OUTPUTS_DIR]:
    os.makedirs(dir_path, exist_ok=True)

SYSTEM_PROMPT_FILE = "system_prompt.md"

ALIBABA_MAAS_BASE_URL = f"https://{WORKSPACE_ID}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1" if WORKSPACE_ID else ""

BAIDU_OCR_TOKEN_URL = "https://aip.baidubce.com/oauth/2.0/token"
BAIDU_OCR_API_URL = "https://aip.baidubce.com/rest/2.0/ocr/v1/multiple_invoice"

def check_config():
    errors = []
    if not DASHSCOPE_API_KEY:
        errors.append("[FAIL] DASHSCOPE_API_KEY 未配置")
    if not WORKSPACE_ID:
        errors.append("[FAIL] WORKSPACE_ID 未配置")
    if not BAIDU_OCR_API_KEY:
        errors.append("[FAIL] BAIDU_OCR_API_KEY 未配置")
    if not BAIDU_OCR_SECRET_KEY:
        errors.append("[FAIL] BAIDU_OCR_SECRET_KEY 未配置")
    if errors:
        raise RuntimeError("配置错误：\n" + "\n".join(errors))
    print("[OK] 配置检查通过")

if __name__ == "__main__":
    check_config()
    print(f"工作目录: {WORK_ROOT}")
    print(f"数据目录: {DATA_DIR}")
    print(f"输出目录: {OUTPUTS_DIR}")