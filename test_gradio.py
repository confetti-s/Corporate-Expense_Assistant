import sys
sys.path.insert(0, '.')

print("1. 导入Gradio...")
import gradio as gr
print(f"   Gradio版本: {gr.__version__}")

print("2. 创建Blocks...")
demo = gr.Blocks()

print("3. 添加简单组件...")
with demo:
    gr.Markdown("# 测试页面")
    gr.Textbox(label="输入")

print("4. 启动Demo...")
try:
    demo.launch(server_name='127.0.0.1', server_port=7860)
    print("5. 启动成功！")
except Exception as e:
    print(f"启动失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()