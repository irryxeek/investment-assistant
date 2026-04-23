#!/bin/bash
# 初始化项目环境
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== 初始化投资助手 ==="

# 安装 /driven skill
SKILL_SRC="$SCRIPT_DIR/driven_SKILL.md"
SKILL_DST="$HOME/.claude/skills/driven/SKILL.md"
if [ -f "$SKILL_SRC" ]; then
    mkdir -p "$(dirname "$SKILL_DST")"
    if [ ! -f "$SKILL_DST" ] || ! diff -q "$SKILL_SRC" "$SKILL_DST" > /dev/null 2>&1; then
        cp "$SKILL_SRC" "$SKILL_DST"
        echo "已安装 /driven skill → $SKILL_DST"
    else
        echo "/driven skill 已是最新"
    fi
fi

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "创建 Python 虚拟环境..."
    python3 -m venv venv
else
    echo "虚拟环境已存在，跳过创建"
fi

# 安装依赖
echo "安装依赖..."
venv/bin/pip install -r requirements.txt -q

# 创建个人数据文件（如不存在）
if [ ! -f "config.json" ]; then
    cp config.example.json config.json
    echo "已创建 config.json（请根据实际持仓修改）"
fi

if [ ! -f "holding_input.txt" ]; then
    cp holding_input.example.txt holding_input.txt
    echo "已创建 holding_input.txt（请替换为实际持仓数据）"
fi

if [ ! -f "trade_history.md" ]; then
    cp trade_history.example.md trade_history.md
    echo "已创建 trade_history.md（请记录实际操作）"
fi

if [ ! -f "trading_rules.md" ]; then
    cp trading_rules.example.md trading_rules.md
    echo "已创建 trading_rules.md（请根据个人风险偏好修改规则阈值）"
fi

# 设置执行权限
chmod +x analyze.sh

echo ""
echo "=== 初始化完成 ==="
echo "下一步："
echo "  1. 编辑 config.json，配置你的持仓标的"
echo "  2. 编辑 holding_input.txt，粘贴实际持仓数据"
echo "  3. 运行 venv/bin/python3 update_holding.py 生成持仓清单"
echo "  4. 运行 venv/bin/python3 fetch_market_data.py 抓取行情数据"
echo "  5. 运行 ./analyze.sh 或 claude /driven 生成分析报告"
