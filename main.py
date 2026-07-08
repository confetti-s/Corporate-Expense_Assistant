import sys
import os
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Gradio 6.x 使用的 Starlette 常量已弃用，过滤第三方库的内部警告
warnings.filterwarnings("ignore", category=DeprecationWarning, module="gradio")

from UI.app import demo
from UI.constants import CUSTOM_CSS

if __name__ == "__main__":
    print("启动企业财务报销助手 v3.0...")
    demo.launch(server_name="127.0.0.1", server_port=7860, css=CUSTOM_CSS)
