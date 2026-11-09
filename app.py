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

# Fallback CSV still works
if "df" not in st.session_state:
    st.session_state["df"] = None

uploaded = st.file_uploader("Or upload CSV instead (optional)", type=["csv"])
if uploaded is not None:
    df_csv = pd.read_csv(uploaded)
    st.session_state["df"] = df_csv

df = st.session_state["df"]
if df is not None:
    st.dataframe(df.tail())
    st.line_chart(df.set_index("time")["close"] if "time" in df.columns else df["close"])

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
        code = code.replace("strategy.long", "LONG")
        code = code.replace("strategy.short", "SHORT")
        code = code.replace("strategy.position_size", "position_size")
        code = re.sub(r'alert\(.*\)', '# alert', code)
        code = re.sub(r'label\.new\(.*\)', '# label.new', code)
        code = re.sub(r'line\.new\(.*\)', '# line.new', code)
        code = code.replace("true", "True").replace("false", "False")
        code = re.sub(r'\bna\b', 'None', code)
        code = re.sub(r'color\.\w+', 'blue', code)
        code = code.replace("varip ", "")
        code = code.replace("var ", "")
        code = re.sub(r'if\s*\((.*?)\)\s*', r'if \1:\n    ', code)
        code = code.replace(":=", "=")

        header = "# Converted by PineToPy - " + version_label + " to Python\nimport pandas as pd\nimport numpy as np\n\n# df = pd.read_csv('data.csv')\n# close = df['close']\n\ndef RSI(close, period=14):\n    delta = close.diff()\n    gain = delta.where(delta > 0, 0).rolling(window=period).mean()\n    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()\n    rs = gain / loss\n    return 100 - (100 / (1 + rs))\n\ndef ATR(high, low, close, period=14):\n    tr = pd.concat([high-low, (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)\n    return tr.rolling(window=period).mean()\n\ndef MACD(close, fast=12, slow=26, signal=9):\n    ema_fast = close.ewm(span=fast, adjust=False).mean()\n    ema_slow = close.ewm(span=slow, adjust=False).mean()\n    macd = ema_fast - ema_slow\n    sig = macd.ewm(span=signal, adjust=False).mean()\n    return macd, sig, macd - sig\n\ndef BB(close, period=20, mult=2):\n    basis = close.rolling(window=period).mean()\n    dev = close.rolling(window=period).std()\n    upper = basis + mult * dev\n    lower = basis - mult * dev\n    return upper, basis, lower\n\n"
        final_code = header + code
        st.success("Converted! Detected " + version_label)
        st.code(final_code, language="python")
        st.download_button("Download .py file", final_code, file_name="converted.py")

        if df is not None and 'close' in df.columns:
            st.subheader("📈 Live Backtest Result")
            close = df['close']
            high = df['high'] if 'high' in df.columns else close
            low = df['low'] if 'low' in df.columns else close

            def RSI_fn(c, period=14):
                delta = c.diff()
                gain = delta.where(delta > 0, 0).rolling(window=period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                rs = gain / loss
                return 100 - (100 / (1 + rs))
            def ATR_fn(h, l, c, period=14):
                tr = pd.concat([h-l, (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
                return tr.rolling(window=period).mean()
            def MACD_fn(c, fast=12, slow=26, signal=9):
                ef = c.ewm(span=fast, adjust=False).mean()
                es = c.ewm(span=slow, adjust=False).mean()
                m = ef - es
                s = m.ewm(span=signal, adjust=False).mean()
                return m, s, m - s
            def BB_fn(c, period=20, mult=2):
                basis = c.rolling(window=period).mean()
                dev = c.rolling(window=period).std()
                return basis + mult * dev, basis, basis - mult * dev

            env = {'pd': pd, 'np': np, 'close': close, 'high': high, 'low': low, 'LONG': 1, 'SHORT': -1, 'RSI': RSI_fn, 'ATR': ATR_fn, 'MACD': MACD_fn, 'BB': BB_fn, 'position_size': 0}
            exec(code, env)
            signal_series = None
            if 'longCondition' in env and 'shortCondition' in env:
                signal_series = np.where(env['longCondition'].fillna(False), 1,