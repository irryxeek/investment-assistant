# Project Instructions

## 项目概述
智能投资助手：手动更新持仓数据 → 参考市场行情 → Claude AI 生成调仓建议

## 权限设置
- 在此目录下的所有操作无需确认，直接执行

## 环境
- Python 虚拟环境: `venv/bin/python3`（直接用绝对路径，不依赖 activate）
- 金融数据: akshare + 新浪实时行情 API + 中证指数官网 + multpl.com
- AI 模型: claude-opus-4-6

## 快速开始
### 方式一：Claude Code 交互式配置（推荐）
```bash
git clone <repo-url> && cd investment-assistant
claude          # 启动 Claude Code，告诉它"帮我初始化项目"
```
Claude Code 会读取本文件，自动执行 `setup.sh`，然后交互式引导你配置持仓。

### 方式二：手动配置
```bash
git clone <repo-url> && cd investment-assistant
./setup.sh                              # 创建 venv、装依赖、安装 skill、生成配置模板
vi config.json                          # 配置你的持仓标的
vi holding_input.txt                    # 粘贴实际持仓数据
venv/bin/python3 update_holding.py      # 生成 holding.md
venv/bin/python3 fetch_market_data.py   # 抓取行情
./analyze.sh                            # AI 分析
```

## Claude Code 初始化引导
当用户请求初始化或配置项目时，按以下流程操作：
1. 运行 `./setup.sh` 安装环境和 `/driven` skill
2. 检查 `config.json` 是否存在，不存在则从 `config.example.json` 复制
3. 询问用户持有哪些基金（名称或代码），根据回答自动生成 `config.json`
   - 对于每只基金：通过 akshare 或搜索确定对应的场内 ETF/指数代码和中证估值代码
   - 自动填充 `tracking` 和 `valuation` 字段
4. 询问用户是否有观察仓（只跟踪不持有的标的），添加到 `watchlist`
5. 提示用户将持仓数据粘贴到 `holding_input.txt`，然后运行 `update_holding.py`
6. 运行 `fetch_market_data.py` 验证行情抓取正常

## 项目结构
```
├── setup.sh                       # 初始化脚本（创建 venv、装依赖）
├── requirements.txt               # Python 依赖
├── config.json                    # 持仓配置（个人数据，gitignore）
├── config.example.json            # 持仓配置模板（含字段说明）
├── update_holding.py              # 手动更新持仓数据工具
├── holding_input.txt              # 持仓数据输入（从支付宝复制，gitignore）
├── holding_input.example.txt      # 持仓输入格式示例
├── fetch_market_data.py           # 行情 + 估值 + 资金面抓取
├── analyze.sh                     # 工作流调度（抓行情 → 调用 Claude 分析）
├── holding.md                     # 持仓清单（自动生成，gitignore）
├── trade_history.md               # 投资操作记录（手动维护，gitignore）
├── trade_history.example.md       # 操作记录格式示例
├── market_data.json               # 市场行情数据（自动生成，保留最近30天）
├── latest_summary.md              # 最新行情摘要（自动生成）
└── CLAUDE.md                      # 项目说明
```

## 个性化配置（config.json）
所有持仓相关配置集中在 `config.json`，两个脚本共同读取：
- `update_holding.py` 读取 `name_match` + `fund_code`（名称→代码映射）
- `fetch_market_data.py` 读取 `tracking`（行情数据源）+ `valuation`（估值数据源）

### 添加新持仓步骤
1. 在 `config.json` 的 `funds` 数组中添加一项
2. 填写 `name_match`（基金名称关键字）、`fund_code`（基金代码）
3. 配置 `tracking`：对应的场内 ETF/指数代码和数据源类型
4. 可选配置 `valuation`：估值数据源（`csindex` 或 `multpl`）
5. 如果只想观察不持有，放在 `watchlist` 中

### tracking.market 支持的类型
| market | 说明 | 示例 |
|--------|------|------|
| `a_sina` | A股 ETF/LOF（新浪行情） | `sh518880`, `sz161125` |
| `index_sina` | A股指数（新浪行情） | `sh000510` |
| `index_hk` | 港股指数（akshare） | `HSTECH`, `HSI` |

### valuation.source 支持的类型
| source | 说明 | code 格式 |
|--------|------|-----------|
| `csindex` | 中证指数官网（PE/PB/股息率） | 中证指数代码，如 `000510` |
| `multpl` | multpl.com（标普500专用） | 不需要 code |

## 工作流程
1. **配置持仓**：编辑 `config.json`，定义你的持仓标的和数据源
2. **更新持仓数据**：从支付宝/天天基金复制数据到 `holding_input.txt`
3. **运行更新脚本**：`venv/bin/python3 update_holding.py`（输入现金余额）
4. **抓取行情**：`venv/bin/python3 fetch_market_data.py`
5. **AI 分析**：`./analyze.sh` 或 `claude /driven` 生成报告

## 数据说明
- 实际持有**联接基金**（场外，按净值申赎），行情抓取的是对应**ETF/指数**（场内，实时价格）
- 两者存在跟踪误差，分析时需注意
- 联接基金净值无稳定 API，需手动从基金平台复制

## 注意事项
- **重要**：`holding.md` 由 `update_holding.py` 生成，不要手动编辑
- **重要**：`fetch_market_data.py` 仅抓取市场行情参考，不会更新 `holding.md`
- `/driven` skill 必须作为命令行参数：`claude /driven <<EOF`（不能放在 heredoc 内）
- 新浪 API 需禁用系统代理（脚本已处理）
- 建议每日收盘后（15:00+）更新持仓数据
