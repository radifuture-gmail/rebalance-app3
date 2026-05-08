# v1.0.1 - Forced sync update
import pandas as pd
import numpy as np
from datetime import datetime

# 基準構成比率
BASE_RATIOS = {
    "BOXX": 0.10, "GDE": 0.30, "RSSB": 0.30, "DBMF": 0.30
}

def calculate_dynamic_ratios(indicators, policy_rate):
    """
    動的調整ロジック（BOXX金利調整 + MA乖離調整）を適用した目標比率を算出
    """
    if indicators is None or indicators.empty:
        return BASE_RATIOS.copy()
        
    ratios = BASE_RATIOS.copy()
    non_boxx_tickers = ["GDE", "RSSB", "DBMF"]
    all_tickers = ["BOXX", "GDE", "RSSB", "DBMF"]
    
    # 1. BOXX比率調整
    other_returns = [indicators.loc[t, "return_1m_annualized"] for t in non_boxx_tickers]
    max_other_return = max(max(other_returns), 0.03)
    boxx_diff = policy_rate - max_other_return
    
    if boxx_diff > 0:
        boxx_increase = min(boxx_diff * 3, 0.40 - ratios["BOXX"])
        ratios["BOXX"] += boxx_increase
        for t in non_boxx_tickers:
            ratios[t] -= boxx_increase / len(non_boxx_tickers)

    # 2. MA乖離調整
    reductions = {t: 0.0 for t in non_boxx_tickers}
    for t in non_boxx_tickers:
        ma_1m, ma_3m, ma_200d = indicators.loc[t, ["ma_1m", "ma_3m", "ma_200d"]]
        ma_gap = (ma_3m / ma_200d) - 1
        if ma_gap < -0.03 and not (ma_1m >= ma_3m):
            reduction_amt = ratios[t] * abs(ma_gap)
            reductions[t] = reduction_amt
            ratios[t] -= reduction_amt

    # 3. 再配分
    total_reduction = sum(reductions.values())
    if total_reduction > 0:
        best_ticker = indicators.loc[all_tickers, "return_1m_annualized"].idxmax()
        if best_ticker == "BOXX" and (ratios["BOXX"] + total_reduction) > 0.40:
            allowed = max(0, 0.40 - ratios["BOXX"])
            ratios["BOXX"] += allowed
            remaining = total_reduction - allowed
            if remaining > 0:
                second_best = indicators.loc[non_boxx_tickers, "return_1m_annualized"].idxmax()
                ratios[second_best] += remaining
        else:
            ratios[best_ticker] += total_reduction

    return ratios

def get_virtual_current_holdings(df_prices, policy_rate, initial_capital=100000):
    """
    設定された総額(initial_capital)をターゲット比率通りに保有している場合の『現在の株数』を逆算する。
    """
    if df_prices.empty:
        return {t: 0.0 for t in BASE_RATIOS.keys()}

    # 循環インポートを防ぐために内部でインポート
    try:
        from src.data_loader import calculate_technical_indicators
    except ImportError:
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from src.data_loader import calculate_technical_indicators

    indicators = calculate_technical_indicators(df_prices)
    
    if indicators.empty:
        target_ratios = BASE_RATIOS.copy()
        current_prices = df_prices.iloc[-1]
    else:
        target_ratios = calculate_dynamic_ratios(indicators, policy_rate)
        current_prices = indicators["current_price"].to_dict()

    holdings = {}
    for t, ratio in target_ratios.items():
        price = current_prices[t]
        holdings[t] = (initial_capital * ratio) / price
        
    return holdings

def check_rebalance_trigger(current_holdings, current_prices, target_ratios):
    total_value = sum(current_holdings[t] * current_prices[t] for t in target_ratios)
    if total_value == 0:
        return False, {t: 0.0 for t in target_ratios}, {t: 0.0 for t in target_ratios}
    
    actual_ratios = {t: (current_holdings[t] * current_prices[t]) / total_value for t in target_ratios}
    deviations = {t: actual_ratios[t] - target_ratios[t] for t in target_ratios}
    
    is_required = any(abs(dev) > 0.05 for dev in deviations.values())
    return is_required, actual_ratios, deviations

def calculate_trade_shares(total_value, target_ratios, current_prices, current_holdings):
    actions = []
    for t in target_ratios:
        target_val = total_value * target_ratios[t]
        target_shares = target_val / current_prices[t]
        diff_shares = target_shares - current_holdings[t]
        actions.append({
            "銘柄": t, "現在数": int(current_holdings[t]), "変更後数": int(target_shares),
            "差分": int(diff_shares), "概算約定金額": diff_shares * current_prices[t]
        })
    return pd.DataFrame(actions)