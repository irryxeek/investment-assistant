# Project Instructions

## 项目概述
智能投资助手：手动更新持仓数据 → 参考市场行情 → Claude AI 生成调仓建议

## 权限设置
- 在此目录下的所有操作无需确认，直接执行

## 环境
- Python 虚拟环境: `venv/bin/python3`（直接用绝对路径，不依赖 activate）
- 金融数据: akshare + 新浪实时行情 API（仅供参考）
- AI 模型: claude-opus-4-6

## 项目结构
```
├── update_holding.py      # 手动更新持仓数据工具（主要）
├── holding_input.txt      # 持仓数据输入文件（从支付宝复制）
├── fetch_market_data.py   # 市场行情抓取（仅供参考，不更新持仓）
├── analyze.sh             # 工作流调度（抓行情 → 调用 Claude 分析）
├── holding.md             # 持仓清单（由 update_holding.py 自动生成）
├── trade_history.md       # 投资操作记录（手动维护）
├── market_data.json       # 市场行情数据（自动生成，保留最近30天）
├── latest_summary.md      # 最新行情摘要（自动生成）
└── CLAUDE.md              # 项目说明
```

## 实际持仓（联接基金）
| 标的 | 代码 | 类型 |
|------|------|------|
| 易方达恒生科技 ETF 联接 (QDII) C | 007373 | 场外基金 |
| 景顺长城中证港股通创新药 ETF 联接 C | 014424 | 场外基金 |
| 富国中证 A500 指数增强 C | 021163 | 场外基金 |
| 南方红利低波 50ETF 联接 A | 008736 | 场外基金 |
| 国泰黄金 ETF 联接 C | 004253 | 场外基金 |
| 现金 | CASH | 现金 |

## 工作流程
1. **手动更新持仓**：从支付宝/天天基金复制数据到 `holding_input.txt`
2. **运行更新脚本**：`venv/bin/python3 update_holding.py`（输入现金余额）
3. **参考市场行情**：`fetch_market_data.py` 抓取 ETF 行情作为趋势参考
4. **AI 分析**：`analyze.sh` 或双击 `Analyze.app`，调用 `/driven` skill 生成报告

## 数据更新说明
### 为什么使用手动更新？
- 实际持有**联接基金**（场外，每日一个净值）
- `fetch_market_data.py` 抓取的是**ETF**（场内，实时价格）
- 两者是不同产品，价格/净值更新机制不同
- 联接基金净值需从基金平台获取，无稳定 API

### 手动更新步骤
1. 打开支付宝/天天基金，复制持仓数据
2. 粘贴到 `holding_input.txt`，格式：
   ```
   基金名称,持有金额 (元),持仓收益 (元),昨日收益 (元)
   易方达恒生科技 ETF 联接 (QDII) C,"7,485.33",-725.37,-184.97
   ```
3. 运行 `venv/bin/python3 update_holding.py`
4. 输入现金余额（如 800）
5. 自动生成 `holding.md`

## 注意事项
- **重要**：`holding.md` 由 `update_holding.py` 生成，不要手动编辑
- **重要**：`fetch_market_data.py` 仅抓取市场行情参考，不会更新 `holding.md`
- `/driven` skill 必须作为命令行参数：`claude /driven <<EOF`（不能放在 heredoc 内）
- 新浪 API 需禁用系统代理（脚本已处理）
- 建议每日收盘后（15:00+）更新持仓数据
