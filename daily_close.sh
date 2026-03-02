#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "收盘数据更新 | $(date '+%Y-%m-%d %H:%M:%S')"
echo "=========================================="

# 抓取收盘数据
"$SCRIPT_DIR/venv/bin/python3" fetch_market_data.py || { echo "数据抓取失败"; exit 1; }

# 清理数据（每天只保留最新记录）
"$SCRIPT_DIR/venv/bin/python3" -c "
import json
with open('market_data.json') as f:
    data = json.load(f)

# 按日期分组，每天只保留最新的记录
daily_records = {}
for record in data:
    timestamp = record['timestamp']
    date = timestamp.split()[0]
    if date not in daily_records or timestamp > daily_records[date]['timestamp']:
        daily_records[date] = record

# 按时间排序
result = sorted(daily_records.values(), key=lambda x: x['timestamp'])

with open('market_data.json', 'w') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
"

# 生成今日资产变化报告
"$SCRIPT_DIR/venv/bin/python3" -c "
import json

with open('market_data.json') as f:
    data = json.load(f)

if len(data) >= 2:
    today = data[-1]
    yesterday = data[-2]

    print('\n今日资产变化汇总：')
    print('=' * 50)

    total_today = sum(h.get('当前市值', 0) for h in today['holdings'])
    total_yesterday = sum(h.get('当前市值', 0) for h in yesterday['holdings'])
    total_inflow = sum(h.get('今日净流入', 0) for h in today['holdings'])
    total_change = sum(h.get('今日涨跌额', 0) for h in today['holdings'])

    print(f'昨日总市值: {total_yesterday:.2f} 元')
    print(f'今日总市值: {total_today:.2f} 元')
    print流入: {total_inflow:.2f} 元')
    print(f'今日涨跌额: {total_change:.2f} 元')
    if total_yesterday > 0:
        print(f'今日涨跌幅: {(total_change/total_yesterday*100):.2f}%')
    print()

    print('各持仓今日表现：')
    print('-' * 50)
    for h in today['holdings']:
        name = h['名称']
        change = h.get('今日涨跌额', 0)
        change_pct = h.get('今日涨跌幅', 0)
        inflow = h.get('今日净流入', 0)
        sign = '+' if change >= 0 else ''
        print(f'{name}: {sign}{change:.2f} 元 ({sign}{change_pct:.2f}%)', end='')
        if inflow != 0:
            inflow_sign = '+' if inflow >= 0 else ''
            print(f' [净流入: {inflow_sign}{inflow:.2f}]')
        else:
            print()
else:
    print('\n数据不足，无法计算今日变化（需要至少2天的数据）')
"

echo ""
echo "收盘数据更新完成"
echo "按任意键关闭..."
read -n 1
