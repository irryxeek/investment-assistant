#!/usr/bin/env python3
"""
手动更新持仓数据
从支付宝/天天基金复制持仓数据，粘贴到 holding_input.txt，然后运行此脚本
"""

import os
import re
import csv
from datetime import datetime

LAST_CASH_FILE = os.path.join(os.path.dirname(__file__), '.last_cash.txt')


def load_last_cash():
    if os.path.exists(LAST_CASH_FILE):
        try:
            with open(LAST_CASH_FILE) as f:
                return float(f.read().strip())
        except:
            pass
    return 0


def save_last_cash(cash):
    with open(LAST_CASH_FILE, 'w') as f:
        f.write(str(cash))


def parse_holding_input():
    """解析 holding_input.txt 中的持仓数据"""
    input_file = os.path.join(os.path.dirname(__file__), 'holding_input.txt')

    if not os.path.exists(input_file):
        print(f"错误: 找不到 {input_file}")
        print("请创建 holding_input.txt 并粘贴持仓数据")
        print("\n格式示例:")
        print("基金名称,持有金额 (元),持仓收益 (元),昨日收益 (元)")
        print('易方达恒生科技 ETF 联接 (QDII) C,"7,485.33",-725.37,-184.97')
        return None

    holdings = []
    with open(input_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            # 跳过标题行
            if not row or '基金名称' in row[0] or '标的' in row[0]:
                continue

            if len(row) < 4:
                continue

            name = row[0].strip()
            amount_str = row[1].strip().replace(',', '')
            profit_str = row[2].strip().replace(',', '')
            daily_str = row[3].strip().replace(',', '')

            try:
                amount = float(amount_str)
                profit = float(profit_str)
                daily = float(daily_str)

                holdings.append({
                    'name': name,
                    'amount': amount,
                    'profit': profit,
                    'daily': daily
                })
            except ValueError:
                print(f"警告: 无法解析行: {row}")
                continue

    return holdings


def get_fund_code(name):
    """根据基金名称返回代码（需要手动维护映射）"""
    mapping = {
        '易方达恒生科技': '007373',
        '景顺长城中证港股通创新药': '014424',
        '富国中证 A500': '021163',
        '南方红利低波': '008736',
        '国泰黄金': '004253',
    }

    for key, code in mapping.items():
        if key in name:
            return code

    return 'UNKNOWN'


def update_holding_md(holdings, cash=0):
    """更新 holding.md"""
    holding_file = os.path.join(os.path.dirname(__file__), 'holding.md')

    # 计算汇总
    total_amount = sum(h['amount'] for h in holdings) + cash
    total_profit = sum(h['profit'] for h in holdings)
    total_cost = total_amount - total_profit
    total_return = (total_profit / total_cost * 100) if total_cost else 0
    total_daily = sum(h['daily'] for h in holdings)

    with open(holding_file, 'w', encoding='utf-8') as f:
        f.write("# 持仓清单\n\n")
        f.write("| 标的 | 代码 | 类型 | 持有资产 | 持仓成本 | 持有收益 | 收益率 | 昨日收益 |\n")
        f.write("|------|------|------|----------|----------|----------|--------|----------|\n")

        for h in holdings:
            name = h['name']
            code = get_fund_code(name)
            amount = h['amount']
            profit = h['profit']
            daily = h['daily']
            cost = amount - profit
            return_pct = (profit / cost * 100) if cost else 0

            profit_sign = '+' if profit >= 0 else ''
            return_sign = '+' if return_pct >= 0 else ''
            daily_sign = '+' if daily >= 0 else ''

            f.write(f"| {name} | {code} | 基金 | {amount:,.2f} | {cost:,.2f} | {profit_sign}{profit:.2f} | {return_sign}{return_pct:.2f}% | {daily_sign}{daily:.2f} |\n")

        # 现金行
        if cash > 0:
            f.write(f"| 现金 | CASH | 现金 | {cash:,.2f} | {cash:,.2f} | 0.00 | 0.00% | 0.00 |\n")

        f.write("\n## 汇总\n\n")
        f.write(f"- 总资产: {total_amount:,.2f} 元\n")
        f.write(f"- 总成本: {total_cost:,.2f} 元\n")
        profit_sign = '+' if total_profit >= 0 else ''
        f.write(f"- 总收益: {profit_sign}{total_profit:.2f} 元\n")
        return_sign = '+' if total_return >= 0 else ''
        f.write(f"- 总收益率: {return_sign}{total_return:.2f}%\n")
        daily_sign = '+' if total_daily >= 0 else ''
        f.write(f"- 昨日收益: {daily_sign}{total_daily:.2f} 元\n")

    print(f"✓ 已更新 {holding_file}")
    print(f"\n汇总:")
    print(f"  总资产: {total_amount:,.2f} 元")
    print(f"  总收益: {profit_sign}{total_profit:.2f} 元 ({return_sign}{total_return:.2f}%)")
    print(f"  昨日收益: {daily_sign}{total_daily:.2f} 元")


def main():
    print("=" * 60)
    print("持仓数据更新工具")
    print("=" * 60)

    # 解析输入
    holdings = parse_holding_input()
    if not holdings:
        return

    print(f"\n读取到 {len(holdings)} 条持仓记录:")
    for h in holdings:
        print(f"  - {h['name']}: {h['amount']:.2f} 元")

    # 询问现金余额
    last_cash = load_last_cash()
    prompt = f"\n请输入现金余额 (上次: {last_cash:.0f} 元，直接回车使用上次值): "
    try:
        cash_input = input(prompt).strip()
        cash = float(cash_input) if cash_input else last_cash
    except EOFError:
        cash = last_cash
        print(f"\n现金余额: {last_cash:.0f} 元 (非交互模式，使用上次记录)")
    save_last_cash(cash)

    # 更新 holding.md
    update_holding_md(holdings, cash)

    print("\n完成！")


if __name__ == '__main__':
    main()
