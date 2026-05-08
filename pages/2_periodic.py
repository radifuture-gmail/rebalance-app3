import streamlit as st
from datetime import datetime
from utils.helpers import sync_params_to_url
from src.data_loader import get_etf_data, get_risk_free_rate, calculate_technical_indicators
from src.rebalance_logic import (
    calculate_dynamic_ratios, 
    calculate_trade_shares,
    get_virtual_current_holdings
)
from src.visualizer import (
    plot_price_with_ma, show_metrics, plot_ratio_comparison, 
    show_logic_summary, show_action_table
)

# --- URL同期用ヘルパー関数 ---
def sync_current_state_to_url():
    """現在の総額設定と各銘柄の株数をURLに保存する"""
    params = {
        "capital": st.session_state.get('total_capital', 100000.0),
        "holdings": st.session_state.get('virtual_holdings', {})
    }
    sync_params_to_url(params)

# 1. データ取得
with st.spinner("最新データを取得中..."):
    tickers = ["BOXX", "GDE", "RSSB", "DBMF"]
    df_prices = get_etf_data(tickers)
    policy_rate = get_risk_free_rate()
    indicators = calculate_technical_indicators(df_prices)

if indicators.empty:
    st.error("データの取得または計算に失敗しました。")
    st.stop()

# --- URL同期用ヘルパー関数 ---
def sync_current_state_to_url():
    """現在の総額設定と各銘柄の株数をURLに保存する"""
    params = {
        "capital": st.session_state.get('total_capital', 100000.0),
        "holdings": st.session_state.get('virtual_holdings', {})
    }
    sync_params_to_url(params)

# --- コールバック関数：保有数量のリセット・同期用 ---
def reset_holdings_periodic_callback():
    """設定金額に基づきウィジェットの値を上書きし、URLに同期する"""
    current_capital = st.session_state.get('total_capital', 100000.0)
    new_holdings = get_virtual_current_holdings(
        df_prices, policy_rate, initial_capital=current_capital
    )
    st.session_state['virtual_holdings'] = new_holdings
    st.session_state['last_synced_capital_periodic'] = current_capital
    for t in tickers:
        st.session_state[f"periodic_input_val_{t}"] = float(new_holdings.get(t, 0.0))
    sync_current_state_to_url()

def on_holding_change(ticker):
    """手入力で株数が変更された時にセッションとURLを更新する"""
    st.session_state['virtual_holdings'][ticker] = st.session_state[f"periodic_input_val_{ticker}"]
    sync_current_state_to_url()

def apply_periodic_rebalance_callback(new_shares_dict):
    """リバランス実行後の株数を反映し、URLに同期する"""
    for t, shares in new_shares_dict.items():
        st.session_state['virtual_holdings'][t] = shares
        st.session_state[f"periodic_input_val_{t}"] = shares
    sync_current_state_to_url()

# 2. 初期化判定
# app.py で URL から読込済みの holdings がある場合はそれを優先
total_capital = st.session_state.get('total_capital', 100000.0)

if not st.session_state.get('virtual_holdings'):
    if 'last_synced_capital_periodic' not in st.session_state:
        reset_holdings_periodic_callback()
else:
    # URL 読込済みの値をウィジェット State に同期
    for t in tickers:
        key = f"periodic_input_val_{t}"
        if key not in st.session_state:
            st.session_state[key] = float(st.session_state['virtual_holdings'].get(t, 0.0))
    st.session_state['last_synced_capital_periodic'] = total_capital

# サイドバーのリセットボタン
st.sidebar.button(
    "保有株数を設定金額に合わせてリセット", 
    key="reset_periodic_btn", 
    on_click=reset_holdings_periodic_callback
)

st.title("📅 定期リバランス判定 (Quarterly/Monthly)")
st.info("💡 運用ルール：3, 6, 9, 12月の20日以降で初めに訪れる米国営業日に行う。")

# 3. 定期判定状況の可視化
today = datetime.now()
is_rebalance_month = today.month in [3, 6, 9, 12]
is_after_20th = today.day >= 20
is_periodic_trigger = is_rebalance_month and is_after_20th

st.write(f"本日の日付: **{today.strftime('%Y-%m-%d')}**")
if is_periodic_trigger:
    st.warning("🔔 現在は定期リバランスの実施期間（四半期末）に該当します。")
else:
    st.info("ℹ️ 現在は定期リバランスの実施期間外です。")

# 4. 市場概況
st.header("1. 市場データ・インジケーター")
show_metrics(policy_rate, indicators)
plot_price_with_ma(df_prices, tickers)

# 5. 動的ターゲット比率算出
target_ratios = calculate_dynamic_ratios(indicators, policy_rate)

# 6. 保有状況入力
st.header("2. 保有資産状況")
st.markdown(f"ポートフォリオ基準総額設定: **${total_capital:,.2f}**")

with st.expander("保有数量を手動で調整", expanded=True):
    col_input = st.columns(len(tickers))
    current_holdings = {}
    for i, t in enumerate(tickers):
        key = f"periodic_input_val_{t}"
        current_holdings[t] = col_input[i].number_input(
            f"{t} 保有数量", 
            step=1.0,
            key=key,
            on_change=on_holding_change,
            args=(t,)
        )

current_prices = indicators["current_price"].to_dict()
# 入力された株数に基づく現在の時価合計
actual_current_value = sum(current_holdings[t] * current_prices[t] for t in tickers)
actual_ratios = {t: (current_holdings[t] * current_prices[t]) / actual_current_value if actual_current_value > 0 else 0 for t in tickers}

plot_ratio_comparison(actual_ratios, target_ratios)
st.metric("現在のポートフォリオ合計時価 (入力株数ベース)", f"${actual_current_value:,.2f}")

show_logic_summary(indicators, target_ratios, policy_rate)

# 7. 執行プラン
st.header("3. 執行プラン")
# 【変更】リバランスの基準額を「total_capital」に固定
df_actions = calculate_trade_shares(total_capital, target_ratios, current_prices, current_holdings)
show_action_table(df_actions)

if is_periodic_trigger:
    # 基準総額に基づいたリバランス後の理想株数を算出
    new_shares_after_periodic = {}
    for t in tickers:
        new_shares_after_periodic[t] = float((total_capital * target_ratios[t]) / current_prices[t])

    st.button(
        f"定期リバランスを実行（総額 ${total_capital:,.2f} に調整）", 
        on_click=apply_periodic_rebalance_callback,
        args=(new_shares_after_periodic,)
    )
else:
    st.caption("※現在は期間外のため、上記アクションはターゲット比率に合わせるための参考値です。")