import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

def plot_price_with_ma(df, tickers):
    """
    対象ETFの価格推移と移動平均線のマルチラインチャートを表示
    """
    fig = go.Figure()
    for t in tickers:
        fig.add_trace(go.Scatter(x=df.index, y=df[t], name=f"{t} Price"))
        # 3ヶ月(63日)移動平均線
        ma3 = df[t].rolling(window=63).mean()
        fig.add_trace(go.Scatter(x=df.index, y=ma3, name=f"{t} MA(3M)", line=dict(dash='dot')))
    
    fig.update_layout(title="ETF価格推移と移動平均線", template="plotly_white", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

def show_metrics(policy_rate, indicators):
    """
    政策金利と比較対象ETFのリターンをメトリックカードで表示
    """
    st.subheader("📊 主要インジケーター")
    cols = st.columns(len(indicators) + 1)
    cols[0].metric("米国政策金利 (FF/^IRX)", f"{policy_rate:.2%}")
    for i, (ticker, row) in enumerate(indicators.iterrows()):
        cols[i+1].metric(f"{ticker} 1Mリターン(年換算)", f"{row['return_1m_annualized']:.2%}")

def plot_ratio_comparison(actual_ratios, target_ratios):
    """
    「現在の構成比率」と「理想の構成比率（動的調整後）」を並列表示
    """
    col1, col2 = st.columns(2)
    
    with col1:
        fig_curr = px.pie(values=list(actual_ratios.values()), names=list(actual_ratios.keys()), 
                          title="現在の構成比率", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig_curr, use_container_width=True)
        
    with col2:
        fig_target = px.pie(values=list(target_ratios.values()), names=list(target_ratios.keys()), 
                            title="理想の構成比率 (BOXX・MA調整後)", hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        st.plotly_chart(fig_target, use_container_width=True)

def show_logic_summary(indicators, final_ratios, policy_rate):
    """
    判断過程（BOXX調整、MA乖離など）のサマリーを表示
    """
    st.subheader("💡 判断過程の可視化 (ロジック透明性)")
    
    # BOXX調整の説明
    non_boxx_returns = [indicators.loc[t, "return_1m_annualized"] for t in ["GDE", "RSSB", "DBMF"]]
    max_return = max(max(non_boxx_returns), 0.03)
    boxx_diff = policy_rate - max_return
    
    st.write(f"**1. BOXX比率調整判定:**")
    st.write(f"- 政策金利({policy_rate:.2%}) - max(他ETF 1Mリターン, 3.0%)({max_return:.2%}) = 差分({boxx_diff:.2%})")
    if boxx_diff > 0:
        st.write(f"  → 判定: **BOXX増加対象** (現在目標比率: {final_ratios['BOXX']:.1%})")
    else:
        st.write(f"  → 判定: BOXX増加なし (デフォルト10.0%基準)")

    # MA乖離の説明
    st.write(f"**2. 個別銘柄のMA乖離判定 (GDE/RSSB/DBMF):**")
    summary_data = []
    for ticker in ["GDE", "RSSB", "DBMF"]:
        ma_ratio = (indicators.loc[ticker, "ma_3m"] / indicators.loc[ticker, "ma_200d"]) - 1
        is_recovering = indicators.loc[ticker, "ma_1m"] >= indicators.loc[ticker, "ma_3m"]
        
        status = "正常"
        if ma_ratio < -0.03:
            status = "回復判定により維持" if is_recovering else "減算対象"
        
        summary_data.append({
            "銘柄": ticker,
            "乖離率(3M/200D)": f"{ma_ratio:.2%}",
            "回復判定(1M>=3M)": "YES" if is_recovering else "NO",
            "最終判定": status,
            "最終配分比率": f"{final_ratios[ticker]:.1%}"
        })
    st.table(pd.DataFrame(summary_data))

def show_rebalance_status(is_required, deviations):
    """
    リバランス要否のアラートと乖離度ヒートマップを表示
    """
    if is_required:
        st.error("⚠️ リバランスを推奨します（ターゲット比率から 2σ=5% 以上の乖離を検出）")
    else:
        st.success("✅ 現在ポートフォリオはターゲット比率の許容範囲内です")

    # 乖離度ヒートマップ
    st.write("各銘柄のターゲット比率からの乖離（%ポイント）:")
    dev_df = pd.DataFrame([deviations], index=["乖離"])
    
    try:
        # matplotlibが必要なスタイリング
        styled_df = dev_df.style.background_gradient(cmap='RdBu_r', axis=1, vmin=-0.1, vmax=0.1)
        st.dataframe(styled_df, use_container_width=True)
    except Exception:
        # フォールバック（スタイリングなし）
        st.dataframe(dev_df, use_container_width=True)

def show_action_table(df_actions):
    """
    売買株式数とBefore/Afterの可視化
    """
    st.subheader("🛒 注文予定表 (Action Table)")
    
    def color_diff(val):
        if val > 0: return 'color: #3182ce; font-weight: bold' # 買付: 青
        if val < 0: return 'color: #e53e3e; font-weight: bold' # 売却: 赤
        return ''

    # 【修正箇所】最新のPandasに対応するため applymap ではなく map を使用
    try:
        styled_table = df_actions.style.map(color_diff, subset=['差分'])
    except AttributeError:
        # 古いPandasバージョンのための互換性維持
        styled_table = df_actions.style.applymap(color_diff, subset=['差分'])

    st.dataframe(styled_table, use_container_width=True)

    # Before/After 比較グラフ
    st.write("リバランス前後 保有数量比較")
    fig = px.bar(df_actions, x="銘柄", y=["現在数", "変更後数"], barmode="group",
                 labels={"value": "株式数", "variable": "状態"})
    st.plotly_chart(fig, use_container_width=True)