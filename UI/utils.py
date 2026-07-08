import re


def _render_jump_buttons(text: str) -> str:
    """将 [[Tab名称]] 替换为可点击的 HTML 按钮"""
    TAB_LABELS = {
        "对话报销": "对话报销",
        "预算看板": "预算看板",
        "进度查询": "进度查询",
        "模拟审批": "模拟审批",
    }

    def replacer(match):
        label = match.group(1).strip()
        if label in TAB_LABELS:
            return (
                f'<button '
                f'style="background:#1890ff;color:#fff;border:none;padding:4px 10px;'
                f'border-radius:4px;cursor:pointer;margin:2px;font-size:13px;" '
                f'onclick="document.querySelectorAll(\'button[role=tab]\').forEach('
                f'b=>{{if(b.textContent.trim()===\'{label}\')b.click();}})">'
                f'{label}</button>'
            )

    return re.sub(r'\[\[(.*?)\]\]', replacer, text)


def _tab_visibility_js(show_manager_tabs: bool) -> str:
    """控制预算看板和模拟审批 Tab 的显隐"""
    display = "" if show_manager_tabs else "none"
    return (
        f'<img width="0" height="0" style="display:none" src="" onerror="'
        f"setTimeout(() => {{"
        f"document.querySelectorAll('button[role=tab]').forEach(b => {{"
        f"  const t = b.textContent.trim();"
        f"  if (t === '预算看板' || t === '模拟审批') {{"
        f"    b.style.display = '{display}';"
        f"  }}"
        f"}});"
        f"if ('{display}' === 'none') {{"
        f"  const chatTab = [...document.querySelectorAll('button[role=tab]')].find(b => b.textContent.trim() === '对话报销');"
        f"  if (chatTab) chatTab.click();"
        f"}}"
        f"}}, 150);"
        f'">'
    )
