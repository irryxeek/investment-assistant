#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 提示：现在使用手动更新持仓数据，不再自动抓取 ETF 数据
# 请先运行: venv/bin/python3 update_holding.py
echo "提示: 请确保已运行 update_holding.py 更新持仓数据"
echo ""

# 优先使用用户全局 npm 的 claude（已验证为新版），避免命中旧的 Homebrew 路径
if [ -x "$HOME/.npm-global/bin/claude" ]; then
	CLAUDE_BIN="$HOME/.npm-global/bin/claude"
else
	CLAUDE_BIN="$(command -v claude)"
fi

if [ -z "$CLAUDE_BIN" ] || [ ! -x "$CLAUDE_BIN" ]; then
	echo "未找到可用的 Claude Code CLI，请先安装 @anthropic-ai/claude-code"
	exit 1
fi

# 版本比较：返回 0 表示 $1 >= $2
version_ge() {
	local i
	local IFS=.
	local v1=($1)
	local v2=($2)
	for ((i=${#v1[@]}; i<${#v2[@]}; i++)); do
		v1[i]=0
	done
	for ((i=0; i<${#v1[@]}; i++)); do
		if [ -z "${v2[i]}" ]; then
			v2[i]=0
		fi
		if ((10#${v1[i]} > 10#${v2[i]})); then
			return 0
		fi
		if ((10#${v1[i]} < 10#${v2[i]})); then
			return 1
		fi
	done
	return 0
}

CLAUDE_VERSION="$($CLAUDE_BIN --version 2>/dev/null | awk '{print $1}')"
MIN_VERSION="2.1.78"
if ! version_ge "$CLAUDE_VERSION" "$MIN_VERSION"; then
	echo "Claude Code 版本过低: $CLAUDE_VERSION（需要 >= $MIN_VERSION）"
	echo "请升级: npm install -g @anthropic-ai/claude-code@latest"
	exit 1
fi

# 先抓取大盘行情数据（仅供参考）
"$SCRIPT_DIR/venv/bin/python3" fetch_market_data.py || echo "警告: 行情数据抓取失败，将使用上次缓存的数据继续分析"

# 准备分析数据（分析框架由 /driven skill 定义，这里只传递数据）
ANALYSIS_PROMPT="请根据以下数据分析我的持仓并给出操作建议：

## 我的持仓
$(cat holding.md)

## 历史操作
$(cat trade_history.md)

## 今日行情摘要
$(cat latest_summary.md)"

# 使用 Claude 订阅（清除 API 代理环境变量，走 OAuth 认证）
unset ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL
# /driven 必须作为命令行参数传入，不能放在 stdin/heredoc 中
"$CLAUDE_BIN" --model claude-opus-4-6 --allowedTools "WebSearch" /driven <<EOF
$ANALYSIS_PROMPT
EOF
