import datetime
import holidays
import streamlit as st
import base64
import json

def is_us_business_day(date):
    """
    指定された日が米国の営業日（平日かつ祝日でない）かどうかを判定します。
    """
    us_holidays = holidays.UnitedStates()
    if date.weekday() >= 5:
        return False
    if date in us_holidays:
        return False
    return True

def get_latest_us_business_day(date):
    """
    指定された日以前（当日含む）で、直近の米国の営業日を返します。
    """
    curr = date
    while not is_us_business_day(curr):
        curr -= datetime.timedelta(days=1)
    return curr

def get_first_business_day_on_or_after(date):
    """
    指定された日以降（当日含む）で、最初の米国の営業日を返します。
    """
    curr = date
    while not is_us_business_day(curr):
        curr += datetime.timedelta(days=1)
    return curr

def sync_params_to_url(params_dict):
    """
    【新規】辞書データをJSON化し、Base64エンコードしてURLパラメータ 's' に保存します。
    """
    try:
        json_str = json.dumps(params_dict)
        b64_str = base64.urlsafe_b64encode(json_str.encode()).decode()
        st.query_params["s"] = b64_str
    except Exception as e:
        st.error(f"URL同期エラー: {e}")

def load_params_from_url():
    """
    【新規】URLの 's' パラメータからBase64デコードしてデータを復元します。
    """
    if "s" in st.query_params:
        try:
            b64_str = st.query_params["s"]
            # パディング調整
            missing_padding = len(b64_str) % 4
            if missing_padding:
                b64_str += '=' * (4 - missing_padding)
                
            json_str = base64.urlsafe_b64decode(b64_str.encode()).decode()
            return json.loads(json_str)
        except Exception:
            return {}
    return {}