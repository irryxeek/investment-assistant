#!/usr/bin/env python3
"""
定时抓取持仓标的行情数据
每个交易日 14:40 运行
数据维度参考 Driven 金融分析师 skill：
- 实时行情（价格、涨跌幅）
- 技术指标（MA、RSI、MACD）
- 区间位置（20日/60日高低点）
- 成交量变化
- 历史表现（近5日、近20日）
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import sys
import requests
import json

os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)

# 禁用代理
session = requests.Session()
session.trust_env = False
session.proxies = {'http': None, 'https': None}

# 持仓清单
HOLDINGS = {
    '黄金ETF': {
        'code': 'sh518880',
        'sina_code': 'sh518880',
        'market': 'a_sina',
        'type': 'etf',
        'hist_code': 'sh518880',
        'display_name': '黄金ETF联接C',
    },
    '中证A500': {
        'code': 'sh000510',
        'sina_code': 'sh000510',
        'market': 'index_sina',
        'type': 'index',
        'hist_code': 'sh000510',
        'display_name': 'A500指数增强C',
    },
    '红利低波50ETF': {
        'code': 'sh515450',
        'sina_code': 'sh515450',
        'market': 'a_sina',
        'type': 'etf',
        'hist_code': 'sh515450',
        'display_name': '红利低波50联接A',
    },
    '恒生科技指数': {
        'code': 'HSTECH',
        'sina_code': 'HSTECH',
        'market': 'index_hk',
        'type': 'index',
        'hist_code': 'HSTECH',  # 用 akshare
        'display_name': '恒生科技联接C',
    },
    '港股通创新药ETF': {
        'code': 'sh513120',
        'sina_code': 'sh513120',
        'market': 'a_sina',
        'type': 'etf',
        'hist_code': 'sh513120',
        'index_code': '931250',
        'note': '中证港股通创新药指数ETF',
        'display_name': '创新药联接C',
    },
    '标普500LOF': {
        'code': 'sz161125',
        'sina_code': 'sz161125',
        'market': 'a_sina',
        'type': 'lof',
        'hist_code': 'sz161125',
        'note': '易方达标普500指数LOF（观察仓，未实际持有）',
        'display_name': '标普500LOF（观察）',
    },
}


def fetch_sina_quote(code):
    """新浪实时行情"""
    url = f'https://hq.sinajs.cn/list={code}'
    headers = {'Referer': 'https://finance.sina.com.cn'}
    try:
        resp = session.get(url, headers=headers, timeout=10)
        resp.encoding = 'gbk'
        text = resp.text
        if '=' not in text or '""' in text:
            return None
        data = text.split('="')[1].rstrip('";').split(',')
        if len(data) < 4:
            return None

        # 场外基金格式: 名称,净值,累计净值,估算净值,估算涨跌幅,日期
        if code.startswith('of'):
            return {
                '最新价': float(data[1]),  # 净值
                '涨跌幅': float(data[4]) if len(data) > 4 else 0,
                '今开': float(data[1]),
                '最高': float(data[1]),
                '最低': float(data[1]),
                '昨收': float(data[1]) / (1 + float(data[4])/100) if len(data) > 4 and float(data[4]) != 0 else float(data[1]),
                '成交量': 0,
            }

        # ETF/股票/指数格式: 名称,今开,昨收,当前价,...
        current = float(data[3])
        prev_close = float(data[2])
        open_price = float(data[1])
        high = float(data[4])
        low = float(data[5])
        volume = float(data[8]) if len(data) > 8 else 0
        change_pct = (current / prev_close - 1) * 100 if prev_close else 0
        return {
            '最新价': current,
            '涨跌幅': round(change_pct, 2),
            '今开': open_price,
            '最高': high,
            '最低': low,
            '昨收': prev_close,
            '成交量': volume,
        }
    except Exception as e:
        print(f"[warn] fetch_sina_quote({code}) failed: {e}", file=sys.stderr)
        return None


def fetch_index_hk(code):
    """港股指数实时行情"""
    try:
        df = ak.stock_hk_index_spot_sina()
        row = df[df['代码'] == code]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            '最新价': float(r.get('最新价', 0)),
            '涨跌幅': float(r.get('涨跌幅', 0)),
            '今开': float(r.get('今开', 0)),
            '最高': float(r.get('最高', 0)),
            '最低': float(r.get('最低', 0)),
            '昨收': float(r.get('昨收', 0)),
            '成交量': 0,
        }
    except Exception as e:
        print(f"[warn] fetch_index_hk({code}) failed: {e}", file=sys.stderr)
        return None


def fetch_index_csindex(code):
    """中证指数官网实时行情"""
    from datetime import datetime
    today = datetime.now().strftime('%Y%m%d')
    url = f'https://www.csindex.com.cn/csindex-home/perf/index-perf?indexCode={code}&startDate={today}&endDate={today}'
    try:
        resp = session.get(url, timeout=10)
        data = resp.json().get('data', [])
        if data:
            d = data[-1]  # 取最新一条
            return {
                '最新价': d.get('close', 0),
                '涨跌幅': d.get('changePct', 0),
                '今开': d.get('open', 0),
                '最高': d.get('high', 0),
                '最低': d.get('low', 0),
                '昨收': d.get('close', 0) - d.get('change', 0),
                '成交量': d.get('tradingVol', 0),
            }
    except Exception as e:
        print(f"[warn] fetch_index_csindex({code}) failed: {e}", file=sys.stderr)
    return None


def fetch_index_em(secid):
    """东方财富指数实时行情 - 用 curl 绕过代理"""
    import subprocess
    url = f'https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47,f60,f170'
    try:
        result = subprocess.run(['curl', '-s', '-m', '10', url], capture_output=True, text=True)
        data = json.loads(result.stdout).get('data', {})
        if data:
            return {
                '最新价': data.get('f43', 0) / 100,
                '涨跌幅': data.get('f170', 0) / 100,
                '今开': data.get('f46', 0) / 100,
                '最高': data.get('f44', 0) / 100,
                '最低': data.get('f45', 0) / 100,
                '昨收': data.get('f60', 0) / 100,
                '成交量': data.get('f47', 0),
            }
    except Exception as e:
        print(f"[warn] fetch_index_em({secid}) failed: {e}", file=sys.stderr)
    return None


def fetch_hist_data(info):
    """获取历史数据用于技术分析"""
    hist_code = info.get('hist_code')
    if not hist_code:
        return None

    try:
        # 恒生科技用 akshare
        if hist_code == 'HSTECH':
            df = ak.stock_hk_index_daily_sina(symbol='HSTECH')
            df = df.rename(columns={'date': '日期', 'close': '收盘', 'high': '最高', 'low': '最低', 'volume': '成交量'})
            return df.tail(80)

        # 中证指数用官网API
        if info.get('market') == 'index_csindex':
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=150)).strftime('%Y%m%d')
            url = f'https://www.csindex.com.cn/csindex-home/perf/index-perf?indexCode={hist_code}&startDate={start_date}&endDate={end_date}'
            resp = session.get(url, timeout=10)
            data = resp.json().get('data', [])
            if data:
                df = pd.DataFrame(data)
                df = df.rename(columns={'tradeDate': '日期', 'close': '收盘', 'high': '最高', 'low': '最低', 'tradingVol': '成交量'})
                return df.tail(80)
            return None

        # 其他用新浪K线接口
        url = f'https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_{hist_code}=/CN_MarketDataService.getKLineData'
        params = {'symbol': hist_code, 'scale': '240', 'ma': 'no', 'datalen': 80}
        headers = {'Referer': 'https://finance.sina.com.cn'}
        resp = session.get(url, params=params, headers=headers, timeout=10)
        text = resp.text
        start = text.find('(') + 1
        end = text.rfind(')')
        data = json.loads(text[start:end])
        df = pd.DataFrame(data)
        df = df.rename(columns={'day': '日期', 'close': '收盘', 'high': '最高', 'low': '最低', 'volume': '成交量'})
        df['收盘'] = df['收盘'].astype(float)
        df['最高'] = df['最高'].astype(float)
        df['最低'] = df['最低'].astype(float)
        return df

    except Exception as e:
        print(f"[warn] fetch_hist_data({hist_code}) failed: {e}", file=sys.stderr)
        return None


def calc_technical_indicators(df):
    """计算技术指标"""
    if df is None or len(df) < 20:
        return {}

    try:
        close = df['收盘'].astype(float)
        high = df['最高'].astype(float)
        low = df['最低'].astype(float)

        # 均线
        ma5 = close.rolling(5).mean().iloc[-1]
        ma10 = close.rolling(10).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else None

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = (100 - (100 / (1 + gain / loss))).iloc[-1]

        # MACD
        exp12 = close.ewm(span=12).mean()
        exp26 = close.ewm(span=26).mean()
        macd = (exp12 - exp26).iloc[-1]
        signal = (exp12 - exp26).ewm(span=9).mean().iloc[-1]

        # 区间位置
        high_20 = high.tail(20).max()
        low_20 = low.tail(20).min()
        current = close.iloc[-1]
        position_20 = (current - low_20) / (high_20 - low_20) * 100 if high_20 != low_20 else 50

        high_60 = high.tail(60).max() if len(high) >= 60 else high.max()
        low_60 = low.tail(60).min() if len(low) >= 60 else low.min()
        position_60 = (current - low_60) / (high_60 - low_60) * 100 if high_60 != low_60 else 50

        # 近期表现
        change_5d = (current / close.iloc[-6] - 1) * 100 if len(close) >= 6 else 0
        change_20d = (current / close.iloc[-21] - 1) * 100 if len(close) >= 21 else 0

        return {
            'MA5': round(ma5, 2),
            'MA10': round(ma10, 2),
            'MA20': round(ma20, 2),
            'MA60': round(ma60, 2) if ma60 is not None else None,
            'RSI': round(rsi, 2),
            'MACD': round(macd, 4),
            'Signal': round(signal, 4),
            '20日高点': round(high_20, 2),
            '20日低点': round(low_20, 2),
            '区间位置': round(position_20, 1),
            '60日高点': round(high_60, 2),
            '60日低点': round(low_60, 2),
            '60日区间位置': round(position_60, 1),
            '近5日涨跌': round(change_5d, 2),
            '近20日涨跌': round(change_20d, 2),
        }
    except Exception as e:
        print(f"[warn] calc_technical_indicators failed: {e}", file=sys.stderr)
        return {}


def get_market_overview():
    """获取大盘概览"""
    overview = {}
    try:
        # 上证指数
        resp = session.get('https://hq.sinajs.cn/list=sh000001',
                          headers={'Referer': 'https://finance.sina.com.cn'}, timeout=10)
        resp.encoding = 'gbk'
        data = resp.text.split('="')[1].rstrip('";').split(',')
        overview['上证指数'] = {'价格': float(data[3]), '涨跌幅': round((float(data[3])/float(data[2])-1)*100, 2)}
    except Exception as e:
        print(f"[warn] 上证指数获取失败: {e}", file=sys.stderr)

    try:
        # 深证成指
        resp = session.get('https://hq.sinajs.cn/list=sz399001',
                          headers={'Referer': 'https://finance.sina.com.cn'}, timeout=10)
        resp.encoding = 'gbk'
        data = resp.text.split('="')[1].rstrip('";').split(',')
        overview['深证成指'] = {'价格': float(data[3]), '涨跌幅': round((float(data[3])/float(data[2])-1)*100, 2)}
    except Exception as e:
        print(f"[warn] 深证成指获取失败: {e}", file=sys.stderr)

    try:
        # 恒生指数
        df = ak.stock_hk_index_spot_sina()
        hsi = df[df['代码'] == 'HSI'].iloc[0]
        overview['恒生指数'] = {'价格': float(hsi['最新价']), '涨跌幅': float(hsi['涨跌幅'])}
    except Exception as e:
        print(f"[warn] 恒生指数获取失败: {e}", file=sys.stderr)

    return overview


def main():
    now = datetime.now()
    report_time = now.strftime('%Y-%m-%d %H:%M:%S')

    print("=" * 70)
    print(f"持仓行情报告 | {report_time}")
    print("=" * 70)

    # 大盘概览
    print("\n【大盘概览】")
    overview = get_market_overview()
    for name, data in overview.items():
        sign = '+' if data['涨跌幅'] >= 0 else ''
        print(f"  {name}: {data['价格']:.2f} ({sign}{data['涨跌幅']}%)")

    # 持仓详情
    print("\n【持仓详情】")
    print("-" * 70)

    results = []
    for name, info in HOLDINGS.items():
        code = info['code']
        market = info['market']

        # 获取实时行情
        if market in ('a_sina', 'index_sina', 'fund_sina'):
            quote = fetch_sina_quote(info['sina_code'])
        elif market == 'index_hk':
            quote = fetch_index_hk(code)
        elif market == 'index_em':
            quote = fetch_index_em(code)
        elif market == 'index_csindex':
            quote = fetch_index_csindex(code)
        else:
            quote = None

        if not quote:
            print(f"\n{name}: 数据获取失败")
            continue

        # 获取历史数据和技术指标
        hist_df = fetch_hist_data(info)
        tech = calc_technical_indicators(hist_df)

        # 合并数据
        display_name = info.get('display_name', name)
        result = {
            '名称': display_name,
            '代码': code,
            '时间': report_time,
            **quote,
            **tech
        }

        results.append(result)

        # 打印详情
        sign = '+' if quote['涨跌幅'] >= 0 else ''
        print(f"\n{name}")
        print(f"  价格: {quote['最新价']:.4f} ({sign}{quote['涨跌幅']}%)")
        print(f"  今日: 开{quote.get('今开', 0):.4f} 高{quote.get('最高', 0):.4f} 低{quote.get('最低', 0):.4f}")

        if tech:
            print(f"  均线: MA5={tech.get('MA5', '-')} MA10={tech.get('MA10', '-')} MA20={tech.get('MA20', '-')} MA60={tech.get('MA60', '-')}")
            print(f"  动量: RSI={tech.get('RSI', '-')} MACD={tech.get('MACD', '-')}")
            print(f"  位置: 20日区间 {tech.get('区间位置', '-')}% (低{tech.get('20日低点', '-')} ~ 高{tech.get('20日高点', '-')})")
            print(f"  位置: 60日区间 {tech.get('60日区间位置', '-')}% (低{tech.get('60日低点', '-')} ~ 高{tech.get('60日高点', '-')})")
            print(f"  表现: 近5日 {tech.get('近5日涨跌', '-')}% | 近20日 {tech.get('近20日涨跌', '-')}%")

    print("\n" + "-" * 70)

    # 保存详细数据到 JSON
    if results:
        json_path = os.path.join(os.path.dirname(__file__), 'market_data.json')

        # 读取现有数据
        existing = []
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[warn] 读取 market_data.json 失败，重新创建: {e}", file=sys.stderr)
                existing = []

        # 追加新数据
        existing.append({
            'timestamp': report_time,
            'overview': overview,
            'holdings': results
        })

        # 清理历史数据：非当日数据只保留每天最后一条
        today = now.date()
        today_records = []
        daily_records = {}

        for record in existing:
            record_time = datetime.strptime(record['timestamp'], '%Y-%m-%d %H:%M:%S')
            record_date = record_time.date()

            if record_date == today:
                today_records.append(record)
            else:
                if record_date not in daily_records or record_time > datetime.strptime(daily_records[record_date]['timestamp'], '%Y-%m-%d %H:%M:%S'):
                    daily_records[record_date] = record

        # 合并：历史（按日期排序）+ 当日
        all_records = [daily_records[d] for d in sorted(daily_records.keys())]
        all_records.extend(today_records)

        # 只保留最近30条
        existing = all_records[-30:]

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

        print(f"\n详细数据已保存到 {json_path}")

    # 生成分析摘要供 Claude 使用
    summary_path = os.path.join(os.path.dirname(__file__), 'latest_summary.md')
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(f"# 持仓行情摘要\n\n")
        f.write(f"**更新时间**: {report_time}\n\n")

        f.write("## 大盘概览\n\n")
        f.write("| 指数 | 价格 | 涨跌幅 |\n")
        f.write("|------|------|--------|\n")
        for name, data in overview.items():
            sign = '+' if data['涨跌幅'] >= 0 else ''
            f.write(f"| {name} | {data['价格']:.2f} | {sign}{data['涨跌幅']}% |\n")

        f.write("\n## 持仓详情\n\n")
        f.write("| 标的 | 最新价 | 今日涨跌 | RSI | MA60 | 20日位置 | 60日位置 | 近5日 | 近20日 |\n")
        f.write("|------|--------|----------|-----|------|----------|----------|-------|--------|\n")
        for r in results:
            sign = '+' if r['涨跌幅'] >= 0 else ''
            sign5 = '+' if r.get('近5日涨跌', 0) >= 0 else ''
            sign20 = '+' if r.get('近20日涨跌', 0) >= 0 else ''
            f.write(f"| {r['名称']} | {r['最新价']:.4f} | {sign}{r['涨跌幅']}% | {r.get('RSI', '-')} | {r.get('MA60', '-')} | {r.get('区间位置', '-')}% | {r.get('60日区间位置', '-')}% | {sign5}{r.get('近5日涨跌', '-')}% | {sign20}{r.get('近20日涨跌', '-')}% |\n")

        f.write("\n## 技术信号\n\n")
        for r in results:
            signals = []
            if r.get('RSI'):
                if r['RSI'] < 30:
                    signals.append("RSI超卖")
                elif r['RSI'] > 70:
                    signals.append("RSI超买")
            if r.get('区间位置'):
                if r['区间位置'] < 20:
                    signals.append("接近20日低点")
                elif r['区间位置'] > 80:
                    signals.append("接近20日高点")
            if r.get('MA5') and r.get('MA20'):
                if r['最新价'] > r['MA5'] > r['MA20']:
                    signals.append("多头排列")
                elif r['最新价'] < r['MA5'] < r['MA20']:
                    signals.append("空头排列")
            if r.get('MA60'):
                if r['最新价'] > r['MA60']:
                    signals.append("站上MA60")
                else:
                    signals.append("跌破MA60")
            if r.get('60日区间位置') is not None:
                if r['60日区间位置'] < 20:
                    signals.append("接近60日低点")
                elif r['60日区间位置'] > 80:
                    signals.append("接近60日高点")

            if signals:
                f.write(f"- **{r['名称']}**: {', '.join(signals)}\n")

    print(f"分析摘要已保存到 {summary_path}")

    # 注意：holding.md 现在通过 update_holding.py 手动更新，不再自动更新

    print("\n可以使用以下命令让 Claude 分析:")
    print(f"  claude -p \"$(cat {summary_path}) 请分析今日持仓表现和调仓建议\"")


if __name__ == '__main__':
    main()
