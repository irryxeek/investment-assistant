#!/usr/bin/env python3
"""
回测脚本 - 在历史数据上模拟当前 trading_rules.md 的执行效果

简化假设（已知偏差）:
1. ETF 历史价代替联接基金净值（跟踪误差 2-5%）
2. 多维度确认：技术信号 + 当日价格行为代理（PE分位/资金流历史不易抓）
3. 忽略 T+1/T+2 申赎延迟，按当日收盘价立即成交
4. 起始状态用 trade_history.md 早期记录估算

用法:
  venv/bin/python3 backtest.py
  venv/bin/python3 backtest.py --start 2026-03-01 --end 2026-04-30
"""

import os
import sys
import json
import argparse
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

import akshare as ak
import pandas as pd
import numpy as np

# 禁用代理
os.environ['NO_PROXY'] = '*'
for k in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(k, None)

session = requests.Session()
session.trust_env = False


# =============================================================================
# 规则定义（从 trading_rules.md 提取，三档结构）
# =============================================================================

# 🔴 铁律
IRON_RULES = {
    'concentration_limit': 0.50,        # 单标的占比上限
    'daily_drop_cooldown': -0.03,       # 单日组合跌幅触发冷静期
    'cash_floor_absolute': 0.08,        # 现金占比绝对底线
    'cash_floor_recovery': 0.12,        # 触发后需恢复至此线
    'weekly_trade_limit': 2,            # 全组合每周最多笔数
}

# 🟡 默认规则（每个标的的减仓/加仓阈值）
FUNDS = {
    '恒生科技': {
        'tracking_code': 'HSTECH',
        'tracking_market': 'index_hk',
        'reduce': {'rsi_min': 42, 'pos20_min': None, 'max_amount': 800, 'min_weight': None},
        'add': {'rsi_max': 30, 'max_amount': 500},
    },
    '创新药': {
        'tracking_code': 'sh513120',
        'tracking_market': 'a_sina',
        'reduce': {'rsi_min': 58, 'pos20_min': 0.75, 'max_amount': 300, 'min_weight': None},
    },
    'A500': {
        'tracking_code': 'sh000510',
        'tracking_market': 'index_sina',
        'reduce': {'rsi_min': 78, 'pos20_min': 0.85, 'max_amount': 300, 'min_weight': 0.25},
        'add': {'rsi_max': 30, 'max_amount': 300},
    },
    '红利低波': {
        'tracking_code': 'sh515450',
        'tracking_market': 'a_sina',
        'reduce': {'rsi_min': 70, 'pos20_min': 0.80, 'max_amount': 300, 'min_weight': None},
    },
    '黄金': {
        'tracking_code': 'sh518880',
        'tracking_market': 'a_sina',
        'reduce': {'rsi_min': 75, 'pos20_min': 0.90, 'max_amount': 300, 'min_weight': None},
        'add': {'rsi_max': 20, 'max_amount': 200},
    },
}

# 频率/冷静期（默认规则）
SAME_FUND_WEEKLY_LIMIT = 1          # 同一标的每周最多 1 次
REVERSE_COOLING_DAYS = 5            # 反向操作冷静期
OVERSOLD_BAN_RSI_LOW = 35           # RSI 从此线以下回升过程中禁止加仓
OVERSOLD_BAN_RSI_RECOVER = 50       # 站稳此线以上才解禁

# 起始状态（基于 trade_history.md 2026-03-02 之前推算）
# 03-02 加仓恒科 1000 之前的状态估算
INITIAL_STATE = {
    'date': '2026-03-01',
    'cash': 2000.0,                                  # 估算
    'holdings': {
        '恒生科技':   {'amount': 7500.0, 'cost': 7500.0},   # 加仓前已持
        '创新药':     {'amount': 2500.0, 'cost': 2500.0},
        'A500':       {'amount': 0.0,    'cost': 0.0},      # 后期才建仓
        '红利低波':   {'amount': 1300.0, 'cost': 1000.0},   # 减仓前
        '黄金':       {'amount': 1500.0, 'cost': 1200.0},
    },
}


# =============================================================================
# 数据获取
# =============================================================================

def call_with_timeout(func, timeout_sec=15, *args, **kwargs):
    with ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_sec)
        except FutureTimeoutError:
            print(f"[warn] {func.__name__} timeout", file=sys.stderr)
            return None


def fetch_history(fund_name, info, days=120):
    """抓取历史 K 线，返回 DataFrame（columns: 日期, 收盘, 最高, 最低）"""
    code = info['tracking_code']
    market = info['tracking_market']

    try:
        if market == 'index_hk':
            df = call_with_timeout(ak.stock_hk_index_daily_sina, 15, symbol=code)
            if df is None:
                return None
            df = df.rename(columns={'date': '日期', 'close': '收盘', 'high': '最高', 'low': '最低'})
            df = df.tail(days).reset_index(drop=True)
            return df

        # 新浪 K 线（A股 ETF/指数）
        url = f'https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_{code}=/CN_MarketDataService.getKLineData'
        params = {'symbol': code, 'scale': '240', 'ma': 'no', 'datalen': days}
        headers = {'Referer': 'https://finance.sina.com.cn'}
        resp = session.get(url, params=params, headers=headers, timeout=15)
        text = resp.text
        start = text.find('(') + 1
        end = text.rfind(')')
        data = json.loads(text[start:end])
        df = pd.DataFrame(data)
        df = df.rename(columns={'day': '日期', 'close': '收盘', 'high': '最高', 'low': '最低'})
        df['收盘'] = df['收盘'].astype(float)
        df['最高'] = df['最高'].astype(float)
        df['最低'] = df['最低'].astype(float)
        return df

    except Exception as e:
        print(f"[error] fetch_history({fund_name}/{code}) failed: {e}", file=sys.stderr)
        return None


def calc_indicators(df):
    """为每一天计算 RSI(14) 和 20日位置，返回原 df 加上新列"""
    if df is None or len(df) < 20:
        return None

    close = df['收盘']
    high = df['最高']
    low = df['最低']

    # RSI(14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / loss))

    # 20日位置：(当前 - 20日低) / (20日高 - 20日低)
    high20 = high.rolling(20).max()
    low20 = low.rolling(20).min()
    df['pos20'] = (close - low20) / (high20 - low20)

    # 当日涨跌幅
    df['change_pct'] = close.pct_change()

    return df


# =============================================================================
# 状态管理
# =============================================================================

class PortfolioState:
    def __init__(self, initial):
        self.date = initial['date']
        self.cash = initial['cash']
        self.holdings = {k: dict(v) for k, v in initial['holdings'].items()}
        self.last_trade_date = {}      # 标的 -> 最近一次操作日期
        self.last_trade_action = {}    # 标的 -> 'add' or 'reduce'
        self.weekly_trades = []        # [(date, fund, action), ...]
        self.cooldown_until = None     # 触发铁律冷静期至（date string）
        self.cash_freeze_until_recover = False  # 现金低于8%后是否需等到12%才能加仓
        self.trade_log = []            # 模拟的交易记录
        self.value_history = []        # 每日组合总价值

    def total_value(self, prices):
        """根据当日价格计算组合总价值。prices: {fund_name: 收盘价}"""
        total = self.cash
        for fund, h in self.holdings.items():
            if h['amount'] > 0 and fund in prices:
                # amount 是上次估值时的金额，现在按价格变化重估
                # 简化：用 cost_per_share 的概念会复杂，这里直接用 amount * (今价/初价比例)
                # 实际：我们维护 amount = 当前市值，每日按涨跌幅更新
                pass
            total += h['amount']
        return total

    def update_holdings_by_price(self, prev_prices, curr_prices):
        """根据价格变化更新持仓市值"""
        for fund, h in self.holdings.items():
            if h['amount'] > 0 and fund in prev_prices and fund in curr_prices:
                if prev_prices[fund] > 0:
                    ratio = curr_prices[fund] / prev_prices[fund]
                    h['amount'] = round(h['amount'] * ratio, 2)

    def weekly_count(self, current_date):
        """统计本周（含 current_date）的交易笔数。同日轮动算 1 笔"""
        d = pd.to_datetime(current_date)
        week_start = d - pd.Timedelta(days=d.dayofweek)  # 本周一
        # 同日多笔合并为 1
        week_dates = set()
        for trade_date, _, _ in self.weekly_trades:
            td = pd.to_datetime(trade_date)
            if td >= week_start and td <= d:
                week_dates.add(str(trade_date))
        return len(week_dates)

    def days_since_last_trade(self, fund, current_date):
        """距离该标的上次操作的交易日数（粗略用日历日）"""
        if fund not in self.last_trade_date:
            return 999
        last = pd.to_datetime(self.last_trade_date[fund])
        curr = pd.to_datetime(current_date)
        return (curr - last).days


# =============================================================================
# 规则引擎
# =============================================================================

def check_iron_rules(state, day_data, current_date):
    """
    返回 (blocked_reasons, allowed_actions)
    blocked_reasons: list of (rule_name, detail) - 已触发的铁律
    allowed_actions: 'all' | 'reduce_only' | 'none'
    """
    blocks = []

    # 单日跌幅冷静期
    if state.cooldown_until and current_date <= state.cooldown_until:
        blocks.append(('单日跌幅冷静期', f'冷静期至 {state.cooldown_until}'))
        return blocks, 'none'

    # 频率天花板
    if state.weekly_count(current_date) >= IRON_RULES['weekly_trade_limit']:
        blocks.append(('全组合频率上限', f'本周已 {IRON_RULES["weekly_trade_limit"]} 笔'))
        return blocks, 'none'

    # 现金极限保护
    total = state.cash + sum(h['amount'] for h in state.holdings.values())
    cash_pct = state.cash / total if total > 0 else 0
    if cash_pct < IRON_RULES['cash_floor_absolute']:
        state.cash_freeze_until_recover = True
    if state.cash_freeze_until_recover:
        if cash_pct < IRON_RULES['cash_floor_recovery']:
            blocks.append(('现金极限保护', f'现金 {cash_pct:.1%} < {IRON_RULES["cash_floor_recovery"]:.0%}'))
            return blocks, 'reduce_only'
        else:
            state.cash_freeze_until_recover = False

    # 集中度硬上限：> 50% 强制减仓优先（不阻止其他操作，但应触发警告）
    for fund, h in state.holdings.items():
        if total > 0 and h['amount'] / total > IRON_RULES['concentration_limit']:
            blocks.append(('集中度硬上限', f'{fund} 占比 {h["amount"]/total:.1%}'))

    return blocks, 'all'


def check_default_rules(fund, action, state, day_data, current_date):
    """
    检查默认规则是否允许某个标的的某种操作
    返回 (allowed: bool, reason: str, suggested_amount: float)
    """
    info = FUNDS[fund]
    rsi = day_data['rsi']
    pos20 = day_data['pos20']
    change_pct = day_data['change_pct']

    if pd.isna(rsi):
        return False, 'RSI 数据缺失', 0

    # 同标的频率
    if state.last_trade_date.get(fund):
        days_ago = state.days_since_last_trade(fund, current_date)
        if days_ago < 7:
            return False, f'同标的本周已操作（{days_ago}日前）', 0

    # 反向操作冷静期
    if action == 'add' and state.last_trade_action.get(fund) == 'reduce':
        if state.days_since_last_trade(fund, current_date) < REVERSE_COOLING_DAYS:
            return False, f'减仓后冷静期内（< {REVERSE_COOLING_DAYS}日）', 0
    if action == 'reduce' and state.last_trade_action.get(fund) == 'add':
        if state.days_since_last_trade(fund, current_date) < REVERSE_COOLING_DAYS:
            return False, f'加仓后冷静期内（< {REVERSE_COOLING_DAYS}日）', 0

    if action == 'reduce':
        rules = info.get('reduce')
        if not rules:
            return False, '无减仓规则', 0
        if rsi <= rules['rsi_min']:
            return False, f'RSI {rsi:.1f} ≤ {rules["rsi_min"]}', 0
        if rules.get('pos20_min') and pos20 < rules['pos20_min']:
            return False, f'20日位置 {pos20:.1%} < {rules["pos20_min"]:.0%}', 0
        # min_weight: A500 减仓需占比已达
        if rules.get('min_weight'):
            total = state.cash + sum(h['amount'] for h in state.holdings.values())
            weight = state.holdings[fund]['amount'] / total if total > 0 else 0
            if weight < rules['min_weight']:
                return False, f'占比 {weight:.1%} < {rules["min_weight"]:.0%}', 0
        # 多维度确认（简化）：技术 + 价格行为
        # 减仓需当日涨幅为正（"反弹日减仓"的代理）
        if pd.isna(change_pct) or change_pct < 0:
            return False, f'多维度确认未通过（当日涨幅 {change_pct:.2%}，需 > 0）', 0

        return True, f'RSI {rsi:.1f} > {rules["rsi_min"]}', rules['max_amount']

    elif action == 'add':
        rules = info.get('add')
        if not rules:
            return False, '无加仓规则', 0
        if rsi >= rules['rsi_max']:
            return False, f'RSI {rsi:.1f} ≥ {rules["rsi_max"]}', 0
        # 多维度确认（简化）：极端超卖区已是技术信号，再要求价格非暴跌
        if pd.notna(change_pct) and change_pct < -0.05:
            return False, f'当日大跌 {change_pct:.2%}，避免接飞刀', 0

        return True, f'RSI {rsi:.1f} < {rules["rsi_max"]}', rules['max_amount']

    return False, '未知 action', 0


def execute_trade(state, fund, action, amount, current_date, reason):
    """执行模拟交易"""
    if action == 'reduce':
        if state.holdings[fund]['amount'] < amount:
            amount = state.holdings[fund]['amount']
        if amount <= 0:
            return False
        # 减仓：按当前 amount 比例减少 cost
        if state.holdings[fund]['amount'] > 0:
            ratio = amount / state.holdings[fund]['amount']
            state.holdings[fund]['cost'] = round(state.holdings[fund]['cost'] * (1 - ratio), 2)
        state.holdings[fund]['amount'] = round(state.holdings[fund]['amount'] - amount, 2)
        state.cash = round(state.cash + amount, 2)
    elif action == 'add':
        if state.cash < amount:
            amount = state.cash
        if amount <= 0:
            return False
        state.holdings[fund]['amount'] = round(state.holdings[fund]['amount'] + amount, 2)
        state.holdings[fund]['cost'] = round(state.holdings[fund]['cost'] + amount, 2)
        state.cash = round(state.cash - amount, 2)
    else:
        return False

    state.last_trade_date[fund] = current_date
    state.last_trade_action[fund] = action
    state.weekly_trades.append((current_date, fund, action))
    state.trade_log.append({
        'date': current_date,
        'fund': fund,
        'action': action,
        'amount': amount,
        'reason': reason,
    })
    return True


# =============================================================================
# 主函数
# =============================================================================

def get_day_prices(history, date_str):
    """从所有标的的历史数据中提取某天的收盘价"""
    prices = {}
    for fund, df in history.items():
        row = df[df['日期'].astype(str) == date_str]
        if not row.empty:
            prices[fund] = float(row['收盘'].iloc[0])
    return prices


def get_day_indicators(history, date_str):
    """提取某天的技术指标"""
    indicators = {}
    for fund, df in history.items():
        row = df[df['日期'].astype(str) == date_str]
        if not row.empty:
            indicators[fund] = {
                'rsi': float(row['rsi'].iloc[0]) if pd.notna(row['rsi'].iloc[0]) else float('nan'),
                'pos20': float(row['pos20'].iloc[0]) if pd.notna(row['pos20'].iloc[0]) else float('nan'),
                'change_pct': float(row['change_pct'].iloc[0]) if pd.notna(row['change_pct'].iloc[0]) else float('nan'),
                'close': float(row['收盘'].iloc[0]),
            }
    return indicators


def run_backtest(history, common_dates, initial_state):
    """主回测循环"""
    state = PortfolioState(initial_state)
    prev_prices = None
    skipped_signals = []  # 因规则未通过被跳过的信号

    for date_str in common_dates:
        prices = get_day_prices(history, date_str)
        indicators = get_day_indicators(history, date_str)

        # Step 1: 按价格变化更新组合市值
        if prev_prices:
            state.update_holdings_by_price(prev_prices, prices)
        prev_prices = prices

        # 单日组合跌幅检查
        if state.value_history:
            yesterday_total = state.value_history[-1]['total']
            today_total = state.cash + sum(h['amount'] for h in state.holdings.values())
            daily_change = (today_total - yesterday_total) / yesterday_total if yesterday_total else 0
            if daily_change < IRON_RULES['daily_drop_cooldown']:
                # 触发冷静期：明天禁止任何操作
                next_day_idx = common_dates.index(date_str) + 1
                if next_day_idx < len(common_dates):
                    state.cooldown_until = common_dates[next_day_idx]

        # Step 2: 校验铁律
        iron_blocks, allowed = check_iron_rules(state, indicators, date_str)

        # Step 3: 对每个标的尝试规则评估
        if allowed != 'none':
            for fund in FUNDS:
                if fund not in indicators:
                    continue
                day_data = indicators[fund]

                # 优先 reduce（如果集中度超限，强制减仓优先）
                for action in ['reduce', 'add']:
                    if allowed == 'reduce_only' and action == 'add':
                        continue
                    ok, reason, suggested = check_default_rules(fund, action, state, day_data, date_str)
                    if ok and suggested > 0:
                        # 二次校验：本次操作不能突破频率上限
                        if state.weekly_count(date_str) >= IRON_RULES['weekly_trade_limit']:
                            skipped_signals.append({
                                'date': date_str, 'fund': fund, 'action': action,
                                'reason': '本周已达 2 笔上限',
                            })
                            break
                        # 执行
                        execute_trade(state, fund, action, suggested, date_str, reason)
                        break  # 同一标的当日只考虑一种 action
                    elif not ok and ('RSI' in reason or '位置' in reason or '占比' in reason):
                        # 仅记录关键拦截，避免日志爆炸
                        pass

        # Step 4: 记录当日组合价值
        total = state.cash + sum(h['amount'] for h in state.holdings.values())
        state.value_history.append({
            'date': date_str,
            'total': round(total, 2),
            'cash': state.cash,
            'cash_pct': round(state.cash / total, 4) if total > 0 else 0,
            'iron_blocks': iron_blocks,
        })

    return state


def generate_report(state, common_dates):
    """输出回测报告"""
    out = []
    out.append("# 回测报告\n")
    out.append(f"**回测期**: {common_dates[0]} ~ {common_dates[-1]} ({len(common_dates)} 个交易日)\n")
    out.append(f"**起始总资产**: {INITIAL_STATE['cash'] + sum(h['amount'] for h in INITIAL_STATE['holdings'].values()):,.2f} 元")

    final_total = state.value_history[-1]['total']
    initial_total = INITIAL_STATE['cash'] + sum(h['amount'] for h in INITIAL_STATE['holdings'].values())
    pnl = final_total - initial_total
    pnl_pct = pnl / initial_total * 100

    out.append(f"**最终总资产**: {final_total:,.2f} 元")
    out.append(f"**回测收益**: {pnl:+,.2f} 元 ({pnl_pct:+.2f}%)")
    out.append(f"**触发交易笔数**: {len(state.trade_log)}\n")

    # 实际交易对比（从 trade_history.md 统计）
    out.append("## 模拟 vs 实际\n")
    out.append("| 维度 | 新规则模拟 | 实际操作 |")
    out.append("|------|-----------|---------|")
    out.append(f"| 总交易笔数 | {len(state.trade_log)} | 14 笔（3/2 - 4/16）|")
    reduce_count = sum(1 for t in state.trade_log if t['action'] == 'reduce')
    add_count = sum(1 for t in state.trade_log if t['action'] == 'add')
    out.append(f"| 减仓笔数 | {reduce_count} | 8 笔 |")
    out.append(f"| 加仓笔数 | {add_count} | 6 笔 |")

    # 触发的交易明细
    out.append("\n## 模拟触发的交易\n")
    if state.trade_log:
        out.append("| 日期 | 标的 | 操作 | 金额 | 触发理由 |")
        out.append("|------|------|------|------|----------|")
        for t in state.trade_log:
            action_cn = '减仓' if t['action'] == 'reduce' else '加仓'
            out.append(f"| {t['date']} | {t['fund']} | {action_cn} | {t['amount']:.0f} | {t['reason']} |")
    else:
        out.append("*回测期内无任何规则触发交易*")

    # 铁律触发
    iron_triggers = [v for v in state.value_history if v['iron_blocks']]
    out.append(f"\n## 铁律触发 ({len(iron_triggers)} 天)\n")
    if iron_triggers:
        seen = set()
        for v in iron_triggers[:10]:
            for rule, detail in v['iron_blocks']:
                key = (v['date'], rule)
                if key in seen:
                    continue
                seen.add(key)
                out.append(f"- {v['date']}: **{rule}** — {detail}")

    # 组合价值曲线（关键节点）
    out.append("\n## 组合价值曲线（每周一个采样）\n")
    out.append("| 日期 | 总资产 | 现金占比 |")
    out.append("|------|--------|---------|")
    sampled = state.value_history[::5]  # 每 5 天采样
    for v in sampled:
        out.append(f"| {v['date']} | {v['total']:,.2f} | {v['cash_pct']:.1%} |")

    return '\n'.join(out)


def calc_buy_and_hold_value(history, common_dates):
    """计算"持有不动"策略的最终市值"""
    first_date = common_dates[0]
    last_date = common_dates[-1]
    total = INITIAL_STATE['cash']
    for fund, h in INITIAL_STATE['holdings'].items():
        if h['amount'] <= 0:
            continue
        df = history.get(fund)
        if df is None:
            total += h['amount']
            continue
        first_row = df[df['日期'].astype(str) == first_date]
        last_row = df[df['日期'].astype(str) == last_date]
        if first_row.empty or last_row.empty:
            total += h['amount']
            continue
        ratio = float(last_row['收盘'].iloc[0]) / float(first_row['收盘'].iloc[0])
        total += h['amount'] * ratio
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='2026-03-01')
    parser.add_argument('--end', default=datetime.now().strftime('%Y-%m-%d'))
    parser.add_argument('--days', type=int, default=120, help='抓取多少天历史')
    parser.add_argument('--output', default='backtest_report.md')
    args = parser.parse_args()

    print(f"=== 回测开始 [{args.start} ~ {args.end}] ===\n")

    # Step 1: 抓取所有标的的历史数据
    print("Step 1: 抓取历史数据...")
    history = {}
    for fund_name, info in FUNDS.items():
        df = fetch_history(fund_name, info, days=args.days)
        if df is not None:
            df = calc_indicators(df)
            history[fund_name] = df
            print(f"  {fund_name} ({info['tracking_code']}): {len(df)} 条记录")
        else:
            print(f"  {fund_name}: 抓取失败")

    if not history:
        print("[error] 无法抓取任何历史数据，终止")
        return 1

    # Step 2: 按日期对齐
    common_dates = None
    for fund_name, df in history.items():
        dates = set(df['日期'].astype(str))
        common_dates = dates if common_dates is None else common_dates & dates
    common_dates = sorted([str(d) for d in common_dates
                          if args.start <= str(d) <= args.end])
    print(f"\nStep 2: 回测交易日 {len(common_dates)} 天 [{common_dates[0]} ~ {common_dates[-1]}]")

    # Step 3: 跑回测
    print("\nStep 3: 模拟规则执行...")
    state = run_backtest(history, common_dates, INITIAL_STATE)
    print(f"  共触发 {len(state.trade_log)} 笔模拟交易")

    # 计算持有不动基准
    buy_hold_value = calc_buy_and_hold_value(history, common_dates)
    initial_total = INITIAL_STATE['cash'] + sum(h['amount'] for h in INITIAL_STATE['holdings'].values())
    bh_pnl_pct = (buy_hold_value - initial_total) / initial_total * 100

    # Step 4: 生成报告
    report = generate_report(state, common_dates)
    report += "\n\n## 与持有不动对比\n\n"
    report += "| 策略 | 最终市值 | 收益率 |\n"
    report += "|------|---------|--------|\n"
    final_value = state.value_history[-1]['total']
    rule_pnl_pct = (final_value - initial_total) / initial_total * 100
    report += f"| 新规则模拟 | {final_value:,.2f} | {rule_pnl_pct:+.2f}% |\n"
    report += f"| 持有不动 | {buy_hold_value:,.2f} | {bh_pnl_pct:+.2f}% |\n"
    diff = final_value - buy_hold_value
    report += f"\n**差额**: {diff:+,.2f} 元（规则相对持有不动 {'+' if diff > 0 else ''}{diff/buy_hold_value*100:.2f}%）"

    output_path = os.path.join(os.path.dirname(__file__), args.output)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\nStep 4: 报告已写入 {output_path}")
    print("\n" + "="*60)
    print(report)

    return 0


if __name__ == '__main__':
    sys.exit(main())
