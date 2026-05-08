import streamlit as st
from utils.helpers import load_params_from_url, sync_params_to_url

# 1. ページ設定
st.set_page_config(
    page_title="ETF Rebalance Simulator",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 2. URLパラメータの読み込みと状態の初期化
if 'initialized' not in st.session_state:
    url_params = load_params_from_url()
    
    # ポートフォリオ総額の設定
    st.session_state['total_capital'] = float(url_params.get("capital", 100000.0))
    
    # 保有株数の設定 (URLにあればそれを採用、なければ空にする)
    # 空の場合は各ページの初期化ロジックで「総額」を基準に計算される
    st.session_state['virtual_holdings'] = url_params.get("holdings", {})
    
    st.session_state['initialized'] = True

# 3. URL同期用のヘルパー関数
def sync_all_to_url():
    """現在の総額と保有株数をまとめてURLパラメータに保存する"""
    params = {
        "capital": st.session_state['total_capital'],
        "holdings": st.session_state['virtual_holdings']
    }
    sync_params_to_url(params)

# 4. サイドバー設定
st.sidebar.header("⚙️ 全体設定")

def on_capital_change():
    """総額が変更された時の処理"""
    st.session_state['total_capital'] = st.session_state['capital_input']
    sync_all_to_url()

st.sidebar.number_input(
    "ポートフォリオ総額 ($)", 
    value=st.session_state['total_capital'], 
    step=1000.0,
    format="%.2f",
    key="capital_input",
    on_change=on_capital_change
)

# 5. メインコンテンツとナビゲーション
def show_home():
    st.title("📊 ETF動的リバランス・シミュレーター")
    st.markdown(f"""
    このアプリケーションは、市場データに基づきポートフォリオのリバランス判定を行います。

    ### 🛠 現在の設定
    - **ポートフォリオ基準総額**: `${st.session_state['total_capital']:,.2f}`
    - **株数保存状態**: {"✅ URLから読込済" if st.session_state['virtual_holdings'] else "ℹ️ 総額に基づき自動計算中"}

    ### 📁 メニュー案内
    1. **乖離度リバランス**: 日次での乖離チェックと週次執行ルール。
    2. **定期リバランス**: 四半期末の特定ルールに基づく判定。

    ※各ページで株数を編集したりリバランスを実行すると、URLに状態が保存されます。

    ### ロジック
    政策金利-max(1ヶ月boxx以外の各ETFトータルリターン実績年換算の最大値,3%)がプラスとなった場合に当該プラス×3ずつboxx比率を上げる。ただしboxx比率40%を上限とする。

    リバランスを3ヶ月に一度いれ、加えて乖離度σ2を基準にリバランスする。

    Boxx以外の各ETFのバランス動的調整ロジックとして、3ヶ月移動平均 が 200日移動平均を何%下回ったか(3%以上下回った場合に限る)に応じて当該下回ったETFの構成比率を当該%分減じ、3ヶ月移動平均 と 200日移動平均との比較において一番好調もしくはマシなETF(boxx含む)に加える。ただし1ヶ月移動平均が3ヶ月移動平均以上となっているETFは比率減算対象から除きデフォルトバランスとする。
    これを乖離度リバランスと定期リバランスに組み入れる。

    """)

pg = st.navigation([
    st.Page(show_home, title="ホーム", icon="🏠"),
    st.Page("pages/1_deviation.py", title="1. 乖離度リバランス", icon="🔍"),
    st.Page("pages/2_periodic.py", title="2. 定期リバランス", icon="📅"),
])

# サイドバーへのステータス表示
if "s" in st.query_params:
    st.sidebar.success("設定と株数をURLに同期中")

# 6. 実行
pg.run()