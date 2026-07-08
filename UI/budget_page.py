import re
import tempfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

from src.tools.budget_tool import get_all_department_budgets


def get_budget_chart():
    try:
        budget_info = get_all_department_budgets.func()

        dept_names = []
        budget_amounts = []
        spent_amounts = []
        remaining_amounts = []

        for line in budget_info.split('\n'):
            if '部门名称' in line:
                match = re.search(r'部门名称：(.+?)\s*\(', line)
                if match:
                    dept_names.append(match.group(1).strip())
            elif '总预算' in line:
                match = re.search(r'总预算：([\d,]+(\.\d+)?)\s*元', line)
                if match:
                    budget_amounts.append(float(match.group(1).replace(',', '')))
            elif '已使用' in line:
                match = re.search(r'已使用：([\d,]+(\.\d+)?)\s*元', line)
                if match:
                    spent_amounts.append(float(match.group(1).replace(',', '')))
            elif '剩余预算' in line:
                match = re.search(r'剩余预算：([\d,]+(\.\d+)?)\s*元', line)
                if match:
                    remaining_amounts.append(float(match.group(1).replace(',', '')))

        if not dept_names:
            return None

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

        x = range(len(dept_names))
        ax1.bar(x, budget_amounts, label='总预算', color='#4CAF50', alpha=0.7)
        ax1.bar(x, spent_amounts, label='已使用', color='#FF9800')
        ax1.set_xticks(x)
        ax1.set_xticklabels(dept_names, fontsize=9)
        ax1.set_ylabel('金额（元）')
        ax1.set_title('部门预算使用情况')
        ax1.legend()
        ax1.ticklabel_format(axis='y', style='plain')

        colors = ['#4CAF50', '#8BC34A', '#CDDC39', '#FFC107', '#FF5722']
        ax2.pie(remaining_amounts, labels=dept_names, autopct='%1.1f%%',
                colors=colors[:len(dept_names)])
        ax2.set_title('剩余预算占比')

        plt.tight_layout()
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        plt.savefig(tmp.name, format='png', dpi=100)
        plt.close()
        return tmp.name
    except Exception as e:
        print(f"预算图表生成错误: {e}")
        return None


def update_budget():
    return get_budget_chart(), get_all_department_budgets.func()
