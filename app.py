import streamlit as st
import re
import pandas as pd
import numpy as np
import requests

st.set_page_config(
    page_title="PineToPy",
    page_icon="🌲"
)
st.title("🌲 PineToPy")
st.write("Paste Pine Script, get Python + Live Backtest.")

pine_code = st.text_area(
    "Paste Pine Script here:",
    height=300
)

st.subheader("📊 Live Data")
c1, c2, c3 = st.columns(3)
with c1:
    symbol = st.selectbox(
        "Coin",
        ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    )
with c2:
    interval = st.selectbox(
        "Timeframe",
        ["1d", "4h", "1h", "15m", "1m"]
    )
with c3:
    limit = st.slider("Candles", 100, 1000, 500)

if "df" not in st.session_state:
    st.session_state["df"] = None

if st.button("Fetch Live Data"):
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    r = requests.get(url, params=params, timeout=10)
    data = r.json()
    cols = [
        "time", "open", "high", "low", "close",
        "volume", "close_time", "qav", "trades",
        "taker_base", "taker_quote", "ignore"
    ]
    df_new = pd.DataFrame(data, columns=cols)
    for col in ["open", "high", "low", "close", "volume"]:
        df_new[col] = df_new[col].astype(float)
    df_new["time"] = pd.to_datetime(
        df_new["time"], unit="ms"
    )
    st.session_state["df"] = df_new
    st.success("Fetched live data")

uploaded = st.file_uploader(
    "Or upload CSV",
    type=["csv"]
)
if uploaded is not None:
    st.session_state["df"] = pd.read_csv(uploaded)

df = st.session_state["df"]
if df is not None:
    st.dataframe(df.tail())
    st.line_chart(df["close"])

if st.button("Convert to Python"):
    if not pine_code.strip():
        st.warning("Paste Pine Script first")
    else:
        code = pine_code
        is_v6 = "@version=6" in code
        vlabel = "v6" if is_v6 else "v5"

        code = re.sub(
            r"//@version=.*",
            "# Pine " + vlabel,
            code
        )
        code = re.sub(
            r"indicator\(.*?\)",
            "# Indicator",
            code
        )
        code = re.sub(
            r"strategy\(.*?\)",
            "# Strategy",
            code
        )
        code = re.sub(
            r"input\.int\(\s*(\d+).*?\)",
            r"\1",
            code
        )
        code = re.sub(
            r"input\.float\(\s*([\d\.]+).*?\)",
            r"\1",
            code
        )

        code = code.replace(
            "ta.sma(close,",
            "close.rolling(window="
        )
        code = code.replace(
            "ta.ema(close,",
            "close.ewm(span="
        )
        code = code.replace(
            "ta.rsi(close,",
            "RSI(close,"
        )
        code = code.replace(
            "ta.change(close)",
            "close.diff()"
        )

        code = re.sub(
            r"ta\.atr\(\s*([^\)]+)\)",
            r"ATR(high, low, close, \1)",
            code
        )
        code = re.sub(
            r"ta\.mom\(close,\s*([^\)]+)\)",
            r"close.diff(\1)",
            code
        )
        code = re.sub(
            r"ta\.macd\(close,\s*([^,]+),",
            r"MACD(close, \1,",
            code
        )