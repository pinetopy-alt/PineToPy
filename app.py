import streamlit as st
import re
import pandas as pd
import numpy as np

st.set_page_config(page_title="PineToPy", page_icon="🌲")
st.title("🌲 PineToPy - Pine v5 & v6 to Python")
st.write("Paste Pine Script v5 or v6, get working Python with pandas.")

pine_code = st.text_area("Paste Pine Script here:", height=300, placeholder="//@version=6\nindicator(...)")

st.subheader("📁 Optional: Upload CSV to Backtest")
uploaded = st.file_uploader("Upload OHLC CSV (must have close)", type=["csv"])
df = None
if uploaded is not None:
    df = pd.read_csv(uploaded)
    st.success(f"Loaded {len(df)} rows. Columns: {list(df.columns)}")
    st.dataframe(df.head())

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
        code = re.sub(r'close\.ewm\(span=\s*([^\)]+)\)', r'close.ewm(span=\1, adjust=False).mean()', code)

        code = re.sub(r'ta\.highest\(close,\s*([^\)]+)\)', r'close.rolling(window=\1).max()', code)
        code = re.sub(r'ta\.lowest\(close,\s*([^\)]+)\)', r'close.rolling(window=\1).min()', code)

        code = re.sub(r'request\.security\(.*?\)', '# request.security - load data separately', code)

        code = re.sub(r'plot\(.*\)', '# plot', code)
        code = re.sub(r'plotshape\(.*\)', '# plotshape', code)
        code = re.sub(r'hline\(.*\)', '# hline', code)
        code = re.sub(r'bgcolor\(.*\)', '# bgcolor', code)

        code = code.replace("ta.crossover(fast, slow)", "(fast > slow) & (fast.shift(1) <= slow.shift(1))")
        code = code.replace("ta.crossunder(fast, slow)", "(fast < slow) & (fast.shift(1) >= slow.shift(1))")
        code = re.sub(r'ta\.crossover\((.*?),\s*(.*?)\)', r'(\1 > \2) & (\1.shift(1) <= \2.shift(1))', code)
        code = re.sub(r'ta\.crossunder\((.*?),\s*(.*?)\)', r'(\1 < \2) & (\1.shift(1) >= \2.shift(1))', code)

        code = code.replace("strategy.entry", "# strategy.entry")
        code = code.replace("strategy.close", "# strategy.close")
        code = code.replace("strategy.exit", "# strategy.exit")
        code