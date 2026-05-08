import yfinance as yf
import pandas as pd
import streamlit as st
from datetime import datetime

def get_etf_data(tickers=["PFIX", "COM", "GDE", "RSSB", "DBMF", "BOXX"], period="2y"):
    """
    Yahoo FinanceからETFの価格データを取得する。
    yfinanceは休日のデータを含まないため、最新の行を参照することで自動的に「直近の平日」が取得されます。
    """
    # auto_adjust=False を明示して Adj Close を取得しやすくする
    df = yf.download(tickers, period=period, auto_adjust=False)
    
    # yfinanceのバージョン違いによるMultiIndexの構造変化に対応
    if isinstance(df.columns, pd.MultiIndex):
        if "Adj Close" in df.columns.get_level_values(0):
            data = df["Adj Close"]
        elif "Adj Close" in df.columns.get_level_values(1):
            data = df.xs("Adj Close", axis=1, level=1)
        elif "Close" in df.columns.get_level_values(0):
            data = df["Close"]
        elif "Close" in df.columns.get_level_values(1):
            data = df.xs("Close", axis=1, level=1)
        else:
            st.error("❌ 価格データの抽出に失敗しました。")
            st.stop()
    else:
        if "Adj Close" in df.columns:
            data = df["Adj Close"]
        elif "Close" in df.columns:
            data = df["Close"]
        else:
            st.error("❌ 価格データが見つかりません。")
            st.stop()

    # もし1銘柄しか取得できずSeriesになってしまった場合の保護
    if isinstance(data, pd.Series):
        data = data.to_frame(name=tickers[0] if len(tickers)==1 else "Unknown")

    # 取得失敗・欠損銘柄のチェック（すべてNaNの列も除外）
    valid_tickers = data.dropna(axis=1, how='all').columns
    missing_tickers = [t for t in tickers if t not in valid_tickers]
    
    if missing_tickers:
        st.warning(f"⚠️ Yahoo Financeからのデータ取得エラー: 以下の銘柄のデータが一時的に取得できませんでした: **{', '.join(missing_tickers)}**")
        st.info("💡 理由: Streamlit CloudからのアクセスがYahoo FinanceのAPI制限(Rate Limit)に引っかかっている可能性があります。\n\n**対策**: データが欠損したまま進めると「不足銘柄を誤って全売却指示する」などの致命的な計算エラーが起きるため、安全のために処理を中断しました。数分待ってからページをリロードしてください。")
        st.stop() # 💡ここでアプリを安全に強制停止させます
        
    # 銘柄ごとの休場日の違いを考慮し、欠損値を前方埋め
    data = data.ffill()
    return data

def get_risk_free_rate():
    """
    米短国債利回り(^IRX)を金利指標として取得
    """
    try:
        ticker = yf.Ticker("^IRX")
        # 直近1ヶ月分取得し、その最終営業日の値を採用
        hist = ticker.history(period="1mo")
        if not hist.empty:
            latest_rate = hist['Close'].iloc[-1] / 100.0
            return latest_rate
        return 0.0525
    except Exception:
        return 0.0525

def calculate_technical_indicators(df):
    """
    ロジック判定に必要な移動平均とリターンを計算する
    """
    # データが十分にない場合のハンドリング
    if len(df) < 200:
        return pd.DataFrame()

    indicators = pd.DataFrame(index=df.columns)
    
    # 最新価格（最終行 ＝ 実行時点での最新の平日データ）
    indicators["current_price"] = df.iloc[-1]
    
    # 移動平均 (MA) - 営業日ベース
    indicators["ma_1m"] = df.rolling(window=21).mean().iloc[-1]
    indicators["ma_3m"] = df.rolling(window=63).mean().iloc[-1]
    indicators["ma_200d"] = df.rolling(window=200).mean().iloc[-1]
    
    # 1ヶ月トータルリターン実績（年換算用）
    # (最新の平日価格 / 約21営業日前価格 - 1) * 12
    indicators["return_1m_annualized"] = (df.iloc[-1] / df.iloc[-21] - 1) * 12
    
    return indicators