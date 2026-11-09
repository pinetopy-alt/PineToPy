import streamlit as st
import re
import pandas as pd
import numpy as np
import requests

st.set_page_config(page_title="PineToPy", page_icon="🌲")
st.title("🌲 PineToPy - Pine v5 & v6 to Python")
st.write("Paste Pine Script, get Python + Live Backtest. No CSV needed.")

pine_code = st.text_area("Paste Pine Script here:", height=300, placeholder="//@version=6\nindicator(...)")

# --- LIVE DATA ---
st.subheader("📊 Live Data - No CSV Needed")
col1, col2, col3 = st.columns(3)
with col1:
    symbol = st.selectbox("Coin", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT"])
with col2:
    interval = st.selectbox("Timeframe", ["1d", "4h", "1h", "15m", "1m"], index=0)
with col3:
    limit = st.slider("Candles", 100, 1000, 500)

df = None
if st.button("📡 Fetch Live Data"):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        df = pd.DataFrame(data, columns=["time","open","high","low","close","volume","close_time","qav","trades","taker_base","taker_quote","ignore"])
        for c in ["open","high","low","close","volume"]:
            df[c] = df[c].astype(float)
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        st.session_state["df"] = df
        st.success(f"Fetched {len(df)} live candles for {symbol} {interval}")
    except Exception as e:
        st.error(f"Failed to fetch: {e}. Binance might be blocked, try CSV below.")

if "df" not in st.session_state:
    st.session_state["df"] = None

uploaded = st.file_uploader("Or upload CSV instead (optional)", type=["csv"])
if uploaded is not None:
    df_csv = pd.read_csv(uploaded)
    st.session_state["df"] = df_csv

df = st.session_state["df"]
if df is not None:
    st.dataframe(df.tail())
    if "time" in df.columns:
        st.line_chart(df.set_index("time")["close"])
    else:
        st.line_chart(df["close"])

if st.button("Convert to Python"):
    if not pine_code.strip():
        st.warning("Please paste some Pine Script first.")
    else:
        code = pine_code
        is_v6 = "@version=6" in code
        version_label = "Pine Script v6" if is_v6 else "Pine Script v5"

        code = re.sub(r'//@version=.*', '# ' + version_label, code)
        code = re.sub(r'indicator\(.*?\)', '# Indicator', code)
        code = re.sub(r'strategy\(.*?\)', '# Strategy', code)
        code = re.sub(r'library\(.*?\)', '# Library', code)
        code = re.sub(r'input\.int\(\s*(\d+).*?\)', r'\1', code)
        code = re.sub(r'input\.float\(\s*([\d\.]+).*?\)', r'\1', code)
        code = code.replace("ta.sma(close,", "close.rolling(window=")
        code = code.replace("ta.ema(close,", "close.ewm(span=")
        code = code.replace("ta.wma(close,", "close.rolling(window=")
        code = re.sub(r'ta\.rsi\(close,\s*([^\)]+)\)', r'RSI(close, \1)', code)
        code = re.sub(r'ta\.atr\(\s*([^\)]+)\)', r'ATR(high, low, close, \1)', code)
        code = re.sub(r'ta\.change\(close\)', r'close.diff()', code)
        code = re.sub(r'ta\.mom\(close,\s*([^\)]+)\)', r'close.diff(\1)', code)
        code = re.sub(r'ta\.macd\(close,\s*([^,]+),\s*([^,]+),\s*([^\)]+)\)', r'MACD(close, \1, \2, \3)', code)
        code = re.sub(r'ta\.bb\(close,\s*([^,]+),\s*([^\)]+)\)', r'BB(close, \1, \2)', code)
        code = re.sub(r'close\.rolling\(window=\s*([^\)]+)\)', r'close.rolling(window=\1).mean()', code)
        code = re.sub(r'close\.ewm\(span=\s