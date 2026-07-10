import sys
import os
import warnings

# Windows UTF-8 encoding fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Gradio 6.x 使用的 Starlette 常量已弃用，过滤第三方库的内部警告
warnings.filterwarnings("ignore", category=DeprecationWarning, module="gradio")


def main():
    import uvicorn
    from src.db.database import init_db
    from src.db.seed_data import main as seed_data

    print("=" * 50)
    print("  FinFlow Corp - 企业财务报销助手 v4.0")
    print("  FastAPI + Stitch Frontend")
    print("=" * 50)

    # 初始化数据库
    print("\n[1/2] Initializing database...")
    init_db()
    seed_data()
    print("[OK] Database ready")

    # 启动 FastAPI 服务
    print("\n[2/2] Starting FastAPI server...")
    print("  Frontend: http://127.0.0.1:7860")
    print("  API Docs: http://127.0.0.1:7860/docs")
    print("  Login:    http://127.0.0.1:7860/login")
    print("=" * 50)

    uvicorn.run(
        "api.app:app",
        host="127.0.0.1",
        port=7860,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
