#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 提示：现在使用手动更新持仓数据，不再自动抓取 ETF 数据
# 请先运行: venv/bin/python3 update_holding.py
echo "提示: 请确保已运行 update_holding.py 更新持仓数据"
echo ""

# 先抓取大盘行情数据（仅供参考）
"$SCRIPT_DIR/venv/bin/python3" fetch_market_data.py || { echo "行情数据抓取失败，请检查网络或脚本"; exit 1; }

# 准备分析数据
ANALYSIS_PROMPT="请根据以下数据分析我的持仓表现，并给出具体操作建议：

## 我的持仓
$(cat holding.md)

## 历史操作
$(cat trade_history.md)

## 今日行情摘要
$(cat latest_summary.md)

## 分析要求
1. 结合技术指标（RSI、MACD、均线、20日区间位置）评估每个持仓的短期走势
2. 根据我的持仓成本和当前收益率，判断是否需要调仓
3. 给出当日具体操作建议：加仓/减仓/持有，以及建议的仓位比例
4. 如有异常信号（超买超卖、接近高低点），重点提示
5. 针对现金，给出配置建议

请直接给出结论和操作建议，不需要解释基础概念。"

# 使用交互式模式调用 driven skill
# 通过 printf 发送 /driven 命令和分析数据
printf "/driven\n%s\n" "$ANALYSIS_PROMPT" | /opt/homebrew/bin/claude --model claude-sonnet-4-6
