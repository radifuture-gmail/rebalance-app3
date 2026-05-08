import streamlit as st
import sys
import os

# --- 【最重要】Streamlit Cloud用 パス強制追加ロジック ---
# 実行ファイルからの相対パスではなく、OS上の絶対パスでプロジェクトルートを特定します
current_script_path = os.path.abspath(__file__) # pages/1_deviation.py
project_root = os.path.dirname(os.path.dirname(current_script_path)) # プロジェクトルート

# sys.pathの先頭に追加し、srcフォルダを確実に見つけられるようにします
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# カレントディレクトリもルートに移動（念のため）
os.chdir(project_root)

# インポート前に、パスが正しく通っているか確認（エラーの切り分け用）
try:
    from utils.helpers import sync_params_to_url
    from src.data_loader import get_etf_data, get_risk_free_rate, calculate_technical_indicators
    from src.rebalance_logic import (
        calculate_dynamic_ratios, 
        check_rebalance_trigger, 
        calculate_trade_shares,
        get_virtual_current_holdings
    )
    from src.visualizer import (
        plot_price_with_ma, show_metrics, plot_ratio_comparison, 
        show_logic_summary, show_rebalance_status, show_action_table
    )
except ImportError as e:
    st.error(f"インポートエラーが発生しました。パス設定を確認してください: {e}")
    st.info(f"現在のPython検索パス: {sys.path}")
    st.stop()


st.title("🔍 乖離度リバランス判定 (Daily Check)")

st.info("💡 運用ルール：乖離判定は日次で行うが、リバランス執行は週1回までとする。")

# --- URL同期用ヘルパー関数 ---
def sync_current_state_to_url():
    """現在の総額設定と各銘柄の株数をURLに保存する"""
    params = {
        "capital": st.session_state.get('total_capital', 100000.0),
        "holdings": st.session_state.get('virtual_holdings', {})
    }
    sync_params_to_url(params)

# 1. データ取得
with st.spinner("最新市場データを取得中..."):
    tickers = ["BOXX", "GDE", "RSSB", "DBMF"]
    df_prices = get_etf_data(tickers)
    policy_rate = get_risk_free_rate()
    indicators = calculate_technical_indicators(df_prices)

if indicators.empty:
    st.error("インジケーターの計算に必要なデータが不足しています。")
    st.stop()

# --- 共通ロジック：保有数量をリセット・同期する関数 ---
total_capital = st.session_state.get('total_capital', 100000.0)

def reset_holdings_callback():
    """設定金額に基づき、仮想保有数を計算してリセットする"""
    new_holdings = get_virtual_current_holdings(
        df_prices, policy_rate, initial_capital=st.session_state.get('total_capital', 100000.0)
    )
    st.session_state['virtual_holdings'] = new_holdings
    st.session_state['last_synced_capital_dev'] = st.session_state.get('total_capital', 100000.0)
    for t in tickers:
        st.session_state[f"dev_input_val_{t}"] = float(new_holdings.get(t, 0.0))
    sync_current_state_to_url()

def on_holding_change(ticker):
    """手入力で株数が変更された時にセッションとURLを更新する"""
    st.session_state['virtual_holdings'][ticker] = st.session_state[f"dev_input_val_{ticker}"]
    sync_current_state_to_url()

def apply_rebalance_callback(new_shares_dict):
    """リバランス実行後の株数を反映し、URLに保存する"""
    for t, shares in new_shares_dict.items():
        st.session_state['virtual_holdings'][t] = shares
        st.session_state[f"dev_input_val_{t}"] = shares
    sync_current_state_to_url()

# 2. 初期化判定
# URLから読み込まれた株数（app.pyでセット済み）がある場合は計算をスキップする
if not st.session_state.get('virtual_holdings'):
    if 'last_synced_capital_dev' not in st.session_state:
        reset_holdings_callback()
else:
    # URLから読み込まれた株数がある場合、ウィジェット用Stateに値を同期する
    for t in tickers:
        key = f"dev_input_val_{t}"
        if key not in st.session_state:
            st.session_state[key] = float(st.session_state['virtual_holdings'].get(t, 0.0))
    st.session_state['last_synced_capital_dev'] = total_capital

# サイドバーのリセットボタン
st.sidebar.button(
    "保有株数を設定金額に合わせてリセット", 
    key="reset_dev_btn", 
    on_click=reset_holdings_callback
)

# 3. 市場概況
st.header("1. 市場データ・インジケーター")
show_metrics(policy_rate, indicators)
plot_price_with_ma(df_prices, tickers)

# 4. 動的ターゲット比率算出
target_ratios = calculate_dynamic_ratios(indicators, policy_rate)

# 5. 保有状況入力
st.header("2. 保有資産状況と乖離判定")
st.markdown(f"ポートフォリオ基準総額設定: **${total_capital:,.2f}**")

with st.expander("保有数量を手動で調整", expanded=True):
    col_input = st.columns(len(tickers))
    current_holdings = {}
    for i, t in enumerate(tickers):
        key = f"dev_input_val_{t}"
        current_holdings[t] = col_input[i].number_input(
            f"{t} 保有数量", 
            step=1.0,
            key=key,
            on_change=on_holding_change,
            args=(t,)
        )

# 6. リバランス判定
current_prices = indicators["current_price"].to_dict()
# 入力された株数に基づく「実際の現在価値」
actual_current_value = sum(current_holdings[t] * current_prices[t] for t in tickers)

is_required, actual_ratios, deviations = check_rebalance_trigger(
    current_holdings, current_prices, target_ratios
)

show_rebalance_status(is_required, deviations)
plot_ratio_comparison(actual_ratios, target_ratios)
st.metric("現在のポートフォリオ合計時価 (入力株数ベース)", f"${actual_current_value:,.2f}")

# 7. 判断過程
show_logic_summary(indicators, target_ratios, policy_rate)

# 8. アクション
if is_required:
    st.header("3. 執行プラン")
    # 【変更】リバランス後の計算基準を「設定総額(total_capital)」に固定
    df_actions = calculate_trade_shares(total_capital, target_ratios, current_prices, current_holdings)
    show_action_table(df_actions)
    
    # 執行後の新しい株数（total_capitalを基準に計算）
    new_shares_after_rebalance = {}
    for t in tickers:
        new_shares_after_rebalance[t] = float((total_capital * target_ratios[t]) / current_prices[t])
    
    st.button(
        f"リバランスを実行（総額 ${total_capital:,.2f} に調整）", 
        on_click=apply_rebalance_callback, 
        args=(new_shares_after_rebalance,)
    )
else:
    st.success("現在のポートフォリオは許容範囲内です。")