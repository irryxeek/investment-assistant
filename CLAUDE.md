# Project Instructions

## 项目概述
智能投资助手：自动抓取行情数据 → 技术分析 → Claude AI 生成调仓建议

## 权限设置
- 在此目录下的所有操作无需确认，直接执行

## 环境
- Python 虚拟环境: `venv/bin/python3`（直接用绝对路径，不依赖 activate）
- 金融数据: akshare + 新浪实时行情 API + 中证指数官网 API
- AI 模型: claude-sonnet-4-6

## 项目结构
```
├── fetch_market_data.py   # 行情数据抓取 + 技术指标计算
├── analyze.sh             # 工作流调度（抓数据 → 构建 prompt → 调用 Claude）
├── holding.md             # 持仓清单（手动维护）
├── trade_history.md       # 投资操作记录（手动维护）
├── analyze_prompt.md      # 分析提示词模板
├── market_data.json       # 行情数据（自动生成，保留最近30天）
├── latest_summary.md      # 最新行情摘要（自动生成）
├── analysis_report.txt    # 分析报告（累积存储）
└── Analyze.app (桌面)     # macOS 快捷启动入口
```

## 持仓标的
| 标的 | 代码 | 数据源 |
|------|------|--------|
| 黄金ETF | sh518880 | 新浪实时 |
| 中证A500 | sh000510 | 新浪实时 |
| 红利低波50ETF | sh515450 | 新浪实时 |
| 恒生科技指数 | HSTECH | AKShare |
| 港股通创新药ETF | sh513120 | 新浪实时 |

## 工作流程
1. `fetch_market_data.py` 抓取实时行情 + 计算技术指标（MA/RSI/MACD/区间位置）
2. `analyze.sh` 组装 holding.md + market_data.json + trade_history.md 为完整 prompt
3. 调用 Claude Sonnet 4.6 通过 `/driven` skill 生成分析报告

## 注意事项
- 新浪 API 需禁用系统代理（脚本已处理）
- 中证指数官网 API 盘中不提供当日数据，港股通创新药已改用 ETF 实时行情
- 定时任务建议在 14:40（收盘前）运行
- 修改持仓后需同步更新 `holding.md` 和 `fetch_market_data.py` 中的 HOLDINGS 配置
