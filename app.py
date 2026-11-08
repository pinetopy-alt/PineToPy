import streamlit as st
import re
import pandas as pd
import numpy as np

st.set_page_config(page_title="PineToPy", page_icon="🌲")
st.title("🌲 PineToPy - Pine v5 & v6 to Python")
st.write("Paste Pine Script v5 or v6, get working Python with pandas.")

pine_code = st.text_area("Paste Pine Script here:", height=300, placeholder="//@version=6\nindicator(...)")

# --- CSV Upload ---
st.subheader("📁 Optional: Upload CSV to Backtest")
uploaded = st.file_uploader("Upload OHLC CSV (must have close, or open/high/low/close)", type=["csv"])
df = None
if uploaded is not None:
    try:
        df = pd.read_csv(uploaded)
        st.success(f"Loaded {len(df)} rows. Columns: {list(df.columns)}")
        st.dataframe(df.head())
    except Exception as e:
        st.error(f"CSV error: {e}")

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

        # Inputs
        code = re.sub(r'input\.int\(\s*(\d+).*?\)', r'\1', code)
        code = re.sub(r'input\.float\(\s*([\d\.]+).*?\)', r'\1', code)

        # TA functions - accept variables too
        code = code.replace("ta.sma(close,", "close.rolling(window=")
        code = code.replace("ta.ema(close,", "close.ewm(span=")
        code = code.replace("ta.wma(close,", "close.rolling(window=")
        code = re.sub(r'ta\.rsi\(close,\s*([^\)]+)\)', r'RSI(close, \1)', code)
        code = re.sub(r'ta\.atr\(\s*([^\)]+)\)', r'ATR(high, low, close, \1)', code)
        code = re.sub(r'ta\.change\(close\)', r'close.diff()', code)
        code = re.sub(r'ta\.mom\(close,\s*([^\)]+)\)', r'close.diff(\1)', code)
        code = re.sub(r'ta\.macd\(close,\s*([^,]+),\s*([^,]+),\s*([^\)]+)\)', r'MACD(close, \1, \2, \3)', code)
        code = re.sub(r'ta\.bb\(close,\s*([^,]+),\s*([^\)]+)\)', r'BB(close, \1, \2)', code)

        # Fix rolling / ewm
        code = re.sub(r'close\.rolling\(window=\s*([^\)]+)\)', r'close.rolling(window=\1).mean()', code)
        code = re.sub(r'close\.ewm\(span=\s*([^\)]+)\)', r'close.ewm(span=\1, adjust=False).mean()', code)

        # highest / lowest AFTER rolling fix
        code = re.sub(r'ta\.highest\(close,\s*([^\)]+)\)', r'close.rolling(window=\1).max()', code)
        code = re.sub(r'ta\.lowest\(close,\s*([^\)]+)\)', r'close.rolling(window=\1).min()', code)

        # request.security
        code = re.sub(r'request\.security\(.*?\)', '# request.security - load data separately', code)

        # plot
        code = re.sub(r'plot\(.*\)', '# plot', code)
        code = re.sub(r'plotshape\(.*\)', '# plotshape', code)
        code = re.sub(r'hline\(.*\)', '# hline', code)
        code = re.sub(r'bgcolor\(.*\)', '# bgcolor', code)

        # crossover / crossunder
        code = code.replace("ta.crossover(fast, slow)", "(fast > slow) & (fast.shift(1) <= slow.shift(1))")
        code = code.replace("ta.crossunder(fast, slow)", "(fast < slow) & (fast.shift(1) >= slow.shift(1))")
        code = re.sub(r'ta\.crossover\((.*?),\s*(.*?)\)', r'(\1 > \2) & (\1.shift(1) <= \2.shift(1))', code)
        code = re.sub(r'ta\.crossunder\((.*?),\s*(.*?)\)', r'(\1 < \2) & (\1.shift(1) >= \2.shift(1))', code)

        # strategy
        code = code.replace("strategy.entry", "# strategy.entry")
        code = code.replace("strategy.close", "# strategy.close")
        code = code.replace("strategy.exit", "# strategy.exit")
        code = code.replace("strategy.long", "LONG")
        code = code.replace("strategy.short", "SHORT")
        code = code.replace("strategy.position_size", "position_size")

        # alert / label
        code = re.sub(r'alert\(.*\)', '# alert', code)
        code = re.sub(r'label\.new\(.*\)', '# label.new', code)
        code = re.sub(r'line\.new\(.*\)', '# line.new', code)

        # bool / na / color
        code = code.replace("true", "True").replace("false", "False")
        code = re.sub(r'\bna\b', 'None', code)
        code = re.sub(r'color\.\w+', 'blue', code)

        # var
        code = code.replace("varip ", "")
        code = code.replace("var ", "")

        # if
        code = re.sub(r'if\s*\((.*?)\)\s*', r'if \1:\n    ', code)

        # := to =
        code = code.replace(":=", "=")

        header = "# Converted by PineToPy - " + version_label + " to Python\nimport pandas as pd\nimport numpy as np\n\n# df = pd.read_csv('data.csv')\n# close = df['close']\n\ndef RSI(close, period=14):\n    delta = close.diff()\n    gain = delta.where(delta > 0, 0).rolling(window=period).mean()\n    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()\n    rs = gain / loss\n    return 100 - (100 / (1 + rs))\n\ndef ATR(high, low, close, period=14):\n    tr = pd.concat([high-low, (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)\n    return tr.rolling(window=period).mean()\n\ndef MACD(close, fast=12, slow=26, signal=9):\n    ema_fast = close.ewm(span=fast, adjust=False).mean()\n    ema_slow = close.ewm(span=slow, adjust=False).mean()\n    macd = ema_fast - ema_slow\n    sig = macd.ewm(span=signal, adjust=False).mean()\n    return macd, sig, macd - sig\n\ndef BB(close, period=20, mult=2):\n    basis = close.rolling(window=period).mean()\n    dev = close.rolling(window=period).std()\n    upper = basis + mult * dev\n    lower = basis - mult * dev\n    return upper, basis, lower\n\n"

        final_code = header + code
        st.success("Converted! Detected " + version_label)
        st.code(final_code, language="python")
        st.download_button("Download .py file", final_code, file_name="converted.py")

        # --- BACKTEST ---
        if df is not None and 'close' in df.columns:
            st.subheader("📈 Backtest Result")
            try:
                # Prepare environment to run converted code
                close = df['close']
                high = df['high'] if 'high' in df.columns else close
                low = df['low'] if 'low' in df.columns else close
                open_ = df['open'] if 'open' in df.columns else close
                volume = df['volume'] if 'volume' in df.columns else pd.Series(0, index=df.index)
                LONG = 1
                SHORT = -1

                # Re-define helpers for exec
                def RSI_fn(close_, period=14):
                    delta = close_.diff()
                    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
                    rs = gain / loss
                    return 100 - (100 / (1 + rs))
                def ATR_fn(high_, low_, close_, period=14):
                    tr = pd.concat([high_-low_, (high_-close_.shift(1)).abs(), (low_-close_.shift(1)).abs()], axis=1).max(axis=1)
                    return tr.rolling(window=period).mean()
                def MACD_fn(close_, fast=12, slow=26, signal=9):
                    ema_fast = close_.ewm(span=fast, adjust=False).mean()
                    ema_slow = close_.ewm(span=slow, adjust=False).mean()
                    macd = ema_fast - ema_slow
                    sig = macd.ewm(span=signal, adjust=False).mean()
                    return macd, sig, macd - sig
                def BB_fn(close_, period=20, mult=2):
                    basis = close_.rolling(window=period).mean()
                    dev = close_.rolling(window=period).std()
                    return basis + mult * dev, basis, basis - mult * dev

                env = {
                    'pd': pd, 'np': np, 'close': close, 'high': high, 'low': low,
                    'open': open_, 'volume': volume, 'LONG': LONG, 'SHORT': SHORT,
                    'RSI': RSI_fn, 'ATR': ATR_fn, 'MACD': MACD_fn, 'BB': BB_fn,
                    'position_size': 0
                }
                # Only run the indicator logic part (after header)
                exec(code, env)

                # Find signal: longCondition / shortCondition or rsi logic
                signal_series = None
                if 'longCondition' in env and 'shortCondition' in env:
                    signal_series = np.where(env['longCondition'].fillna(False), 1, np.where(env['shortCondition'].fillna(False), -1, 0))
                elif 'rsi' in env:
                    # RSI strategy fallback: buy <30, sell >70
                    rsi_vals = env['rsi']
                    if hasattr(rsi_vals, 'fillna'):
                        signal_series = np.where(rsi_vals < 30, 1, np.where(rsi_vals > 70, -1, 0))
                
                if signal_series is not None:
                    position = pd.Series(signal_series, index=df.index).replace(0, np.nan).ffill().fillna(0)
                    # Only long for simple backtest
                    position = position.clip(lower=0)
                    returns = close.pct_change().fillna(0)
                    strat_returns = position.shift(1).fillna(0) * returns
                    equity = (1 + strat_returns).cumprod() * 10000
                    buy_hold = (1 + returns).cumprod() * 10000

                    total_return = (equity.iloc[-1] / 10000 - 1) * 100
                    bh_return = (buy_hold.iloc[-1] / 10000 - 1) * 100
                    trades = int((position.diff() != 0).sum())
                   