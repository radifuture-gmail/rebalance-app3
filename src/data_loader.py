import yfinance as yf
import pandas as pd
from datetime import datetime

def get_etf_data(tickers=["BOXX", "GDE", "RSSB", "DBMF"], period="2y"):
    """
    Yahoo FinanceからETFの価格データを取得する。
    yfinanceは休日のデータを含まないため、最新の行を参照することで自動的に「直近の平日」が取得されます。
    """
    # auto_adjust=False を明示して Adj Close を取得しやすくする
    df = yf.download(tickers, period=period, auto_adjust=False)
    
    # カラムがMultiIndexの場合とそうでない場合の両方に対応
    if "Adj Close" in df.columns:
        data = df["Adj Close"]
    elif "Close" in df.columns:
        data = df["Close"]
    else:
        # 万が一取得できなかった場合のエラー回避
        raise KeyError("データの取得に失敗しました。Tickerが正しいか、ネットワークを確認してください。")
        
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