#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 提示：现在使用手动更新持仓数据，不再自动抓取 ETF 数据
# 请先运行: venv/bin/python3 update_holding.py
echo "提示: 请确保已运行 update_holding.py 更新持仓数据"
echo ""

# 先抓取大盘行情数据（仅供参考）
"$SCRIPT_DIR/venv/bin/python3" fetch_market_data.py || { echo "行情数据抓取失败，请检查网络或脚本"; exit 1; }

# 每天只保留最新一条记录，保留多天数据用于趋势分析
"$SCRIPT_DIR/venv/bin/python3" -c "
import json
with open('market_data.json') as f:
    data = json.load(f)

# 按日期分组，每天只保留最新的记录
daily_records = {}
for record in data:
    timestamp = record['timestamp']
    date = timestamp.split()[0]  # 提取日期部分
    # 如果这一天还没有记录，或者当前记录更新，则保留
    if date not in daily_records or timestamp > daily_records[date]['timestamp']:
        daily_records[date] = record

# 按时间排序
result = sorted(daily_records.values(), key=lambda x: x['timestamp'])

with open('market_data.json', 'w') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
"

claude --model claude-sonnet-4-6 /driven <<'EOF'
请根据以下数据分析我的持仓表现，并给出具体操作建议：

## 我的持仓
$(cat holding.md)

## 历史操作
$(cat trade_history.md)

## 今日行情数据
$(cat market_data.json)

## 分析要求
1. 结合技术指标（RSI、MACD、均线、20日区间位置）评估每个持仓的短期走势
2. 根据我的持仓成本和当前收益率，判断是否需要调仓
3. 给出当日具体操作建议：加仓/减仓/持有，以及建议的仓位比例
4. 如有异常信号（超买超卖、接近高低点），重点提示
5. 针对现金，给出配置建议

请直接给出结论和操作建议，不需要解释基础概念。
EOF
