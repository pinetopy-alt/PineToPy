import streamlit as st
import re
import pandas as pd
import numpy as np
import requests
import io

st.set_page_config(
    page_title="PineToPy",
    page_icon="🌲"
)
st.title("🌲 PineToPy")
st.write("Fix for CSV + Live Fetch")

pine_code = st.text_area(
    "Paste Pine Script here:",
    height=250
)

# --- HELPER: FIX CSV ---
def clean_csv(df_raw):
    df = df_raw.copy()
    # 1. Lowercase + strip columns
    new_cols = []
    for c in df.columns:
        cc = str(c).strip().lower()
        cc = cc.replace(" ", "_")
        new_cols.append(cc)
    df.columns = new_cols
    # 2. Rename common names
    rename_map = {}
    for c in df.columns:
        if c in ["date", "datetime", "timestamp", "time"]:
            rename_map[c] = "time"
        if c in ["open", "o"]:
            rename_map[c] = "open"
        if c in ["high", "h"]:
            rename_map[c] = "high"
        if c in ["low", "l"]:
            rename_map[c] = "low"
        if c in ["close", "c", "price", "adj_close", "adjclose"]:
            rename_map[c] = "close"
        if c in ["volume", "vol", "v"]:
            rename_map[c] = "volume"
    df = df.rename(columns=rename_map)
    # 3. If only 1 price col, use it as close
    if "close" not in df.columns:
        for c in df.columns:
            if "price" in c or "close" in c:
                df["close"] = df[c]
    # 4. Make OHLC if missing
    if "close" in df.columns:
        if "open" not in df.columns:
            df["open"] = df["close"]
        if "high" not in df.columns:
            df["high"] = df["close"]
        if "low" not in df.columns:
            df["low"] = df["close"]
        if "volume" not in df.columns:
            df["volume"] = 0
    # 5. Convert to numbers
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"])
    # 6. Parse time
    if "time" in df.columns:
        df["time"] = pd.to_datetime(
            df["time"], errors="coerce", utc=True
        )
        df = df.dropna(subset=["time"])
    else:
        df["time"] = pd.date_range(
            periods=len(df), end=pd.Timestamp.today()
        )
    df = df.sort_values("time")
    df = df.reset_index(drop=True)
    return df

def try_read_csv(file_bytes):
    # Try different delimiters
    for sep in [",", ";", "\t", "|"]:
        try:
            file_bytes.seek(0)
            df_try = pd.read_csv(
                file_bytes, sep=sep, engine="python"
            )
            if len(df_try.columns) >= 2:
                return clean_csv(df_try)
        except Exception:
            continue
    return None

# --- DATA SECTION ---
st.subheader("📊 Data")
tab1, tab2, tab3 = st.tabs(
    ["Live Fetch", "Upload CSV", "Sample Data"]
)

if "df" not in st.session_state:
    st.session_state["df"] = None

with tab1:
    c1, c2, c3 = st.columns(3)
    with c1:
        symbol = st.selectbox(
            "Coin",
            ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
        )
    with c2:
        interval = st.selectbox(
            "Timeframe",
            ["1d", "4h", "1h", "15m"]
        )
    with c3:
        limit = st.slider("Candles", 100, 1000, 500)
    if st.button("Fetch Live Data"):
        st.info("Trying Binance -> Binance US -> Kraken...")
        got = None
        # Try 1: Binance Global
        try:
            url = "https://api.binance.com/api/v3/klines"
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            }
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            if isinstance(data, list):
                cols = ["time", "open", "high", "low", "close",
                        "volume", "ct", "qav", "trades",
                        "tb", "tq", "ig"]
                got = pd.DataFrame(data, columns=cols)
                st.success("Fetched from Binance Global")
        except Exception as e:
            st.warning(f"Binance Global failed: {e}")
        # Try 2: Binance US
        if got is None:
            try:
                url2 = "https://api.binance.us/api/v3/klines"
                params2 = {
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit
                }
                r2 = requests.get(url2, params=params2, timeout=10)
                data2 = r2.json()
                if isinstance(data2, list):
                    cols2 = ["time", "open", "high", "low", "close",
                             "volume", "ct", "qav", "trades",
                             "tb", "tq", "ig"]
                    got = pd.DataFrame(data2, columns=cols2)
                    st.success("Fetched from Binance US")
            except Exception as e:
                st.warning(f"Binance US failed: {e}")
        # Try 3: Kraken via CoinGecko
        if got is None:
            try:
                coin = symbol.replace("USDT", "").lower()
                coin = coin.replace("btc", "bitcoin")
                coin = coin.replace("eth", "ethereum")
                coin = coin.replace("sol", "solana")
                url3 = f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart"
                params3 = {"vs_currency": "usd", "days": "365"}
                r3 = requests.get(url3, params=params3, timeout=15)
                j3 = r3.json()
                prices = j3["prices"]
                got = pd.DataFrame(prices, columns=["time", "close"])
                got["open"] = got["close"]
                got["high"] = got["close"]
                got["low"] = got["close"]
                got["volume"] = 0
                st.success("Fetched from CoinGecko fallback")
            except Exception as e:
                st.error(f"All live sources failed: {e}")
                st.info("Use CSV or Sample Data tab instead")
        if got is not None:
            st.session_state["df"] = clean_csv(got)

with tab2:
    uploaded = st.file_uploader(
        "Upload your CSV - any format",
        type=["csv", "txt"]
    )
    st.caption("Works with: Binance, TradingView, Yahoo, ; or ,")
    if uploaded is not None:
        try:
            bytes_io = io.BytesIO(uploaded.getvalue())
            df_fixed = try_read_csv(bytes_io)
            if df_fixed is not None:
                st.session_state["df"] = df_fixed
                st.success(
                    f"CSV fixed! {len(df_fixed)} rows"
                )
                st.write("Columns found:", list(df_fixed.columns))
            else:
                st.error("Could not read CSV. Check file.")
        except Exception as e:
            st.error(f"CSV error: {e}")
            st.info("Tip: open CSV in Excel, save as CSV UTF-8")

with tab3:
    if st.button("Generate Sample Data Offline"):
        np.random.seed(42)
        n = 500
        dates = pd.date_range(
            end=pd.Timestamp.today(), periods=n
        )
        price = 60000.0
        prices = []
        for i in range(n):
            price = price * (1 + np.random.randn() * 0.02)
            prices.append(price)
        close_s = pd.Series(prices)
        df_new = pd.DataFrame()
        df_new["time"] = dates
        df_new["open"] = close_s
        df_new["high"] = close_s * 1.01
        df_new["low"] = close_s * 0.99
        df_new["close"] = close_s
        df_new["volume"] = 100
        st.session_state["df"] = df_new
        st.success("Sample data ready")

df = st.session_state["df"]
if df is not None:
    st.dataframe(df.tail())
    st.line_chart(df.set_index("time")["close"])
else:
    st.info("No data yet. Fetch live, upload CSV, or sample.")

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
            r"indicator\(.*?\)", "# Indicator", code
        )
        code = re.sub(
            r"strategy\(.*?\)", "# Strategy", code
        )
        code = re.sub(
            r"input\.int\(\s*(\d+).*?\)",
            r"\1", code
        )
        code = re.sub(
            r"input\.float\(\s*([\d\.]+).*?\)",
            r"\1", code
        )
        code = code.replace(
            "ta.sma(close,", "close.rolling(window="
        )
        code = code.replace(
            "ta.ema(close,", "close.ewm(span="
        )
        code = code.replace(
            "ta.rsi(close,", "RSI(close,"
        )
        code = code.replace(
            "ta.change(close)", "close.diff()"
        )
        code = re.sub(
            r"ta\.atr\(\s*([^\)]+)\)",
            r"ATR(high, low, close, \1)", code
        )
        code = re.sub(
            r"ta\.mom\(close,\s*([^\)]+)\)",
            r"close.diff(\1)", code
        )
        code = re.sub(
            r"ta\.macd\(close,\s*([^,]+),",
            r"MACD(close, \1,", code
        )
        code = re.sub(
            r"close\.rolling\(window=([^\)]+)\)",
            r"close.rolling(window=\1).mean()", code
        )
        code = re.sub(
            r"close\.ewm\(span=([^\)]+)\)",
            r"close.ewm(span=\1, adjust=False).mean()", code
        )
        code = re.sub(
            r"ta\.highest\(close,\s*([^\)]+)\)",
            r"close.rolling(window=\1).max()", code
        )
        code = re.sub(
            r"ta\.lowest\(close,\s*([^\)]+)\)",
            r"close.rolling(window=\1).min()", code
        )
        code = re.sub(
            r"ta\.bb\(close,\s*([^,]+),\s*([^\)]+)\)",
            r"BB(close, \1, \2)", code
        )
        code = re.sub(r"plot\(.*\)", "# plot", code)
        code = re.sub(r"hline\(.*\)", "# hline", code)
        code = re.sub(
            r"ta\.crossover\((.*?),\s*(.*?)\)",
            r"(\1 > \2)", code
        )
        code = re.sub(
            r"ta\.crossunder\((.*?),\s*(.*?)\)",
            r"(\1 < \2)", code
        )
        code = code.replace(
            "strategy.entry", "# strategy.entry"
        )
        code = code.replace(
            "strategy.close", "# strategy.close"
        )
        code = code.replace("strategy.long", "LONG")
        code = code.replace("strategy.short", "SHORT")
        code = code.replace("true", "True")
        code = code.replace("false", "False")
        code = re.sub(r"\bna\b", "None", code)
        code = code.replace("varip ", "")
        code = code.replace("var ", "")
        code = re.sub(
            r"if\s*\((.*?)\)\s*", r"if \1:\n    ", code
        )
        code = code.replace(":=", "=")

        header = "# Converted by PineToPy\n"
        header += "import pandas as pd\n"
        header += "import numpy as np\n\n"
        header += "def RSI(close, period=14):\n"
        header += "    delta = close.diff()\n"
        header += "    gain = delta.where(delta > 0, 0)\n"
        header += "    gain = gain.rolling(period).mean()\n"
        header += "    loss = -delta.where(delta < 0, 0)\n"
        header += "    loss = loss.rolling(period).mean()\n"
        header += "    rs = gain / loss\n"
        header += "    return 100 - (100 / (1 + rs))\n\n"
        header += "def ATR(high, low, close, period=14):\n"
        header += "    a = high - low\n"
        header += "    b = (high - close.shift(1)).abs()\n"
        header += "    c = (low - close.shift(1)).abs()\n"
        header += "    tr = pd.concat([a, b, c], axis=1).max(axis=1)\n"
        header += "    return tr.rolling(period).mean()\n\n"
        header += "def MACD(close, fast=12, slow=26, sig=9):\n"
        header += "    ef = close.ewm(span=fast).mean()\n"
        header += "    es = close.ewm(span=slow).mean()\n"
        header += "    m = ef - es\n"
        header += "    s = m.ewm(span=sig).mean()\n"
        header += "    return m, s, m - s\n\n"
        header += "def BB(close, period=20, mult=2):\n"
        header += "    basis = close.rolling(period).mean()\n"
        header += "    dev = close.rolling(period).std()\n"
        header += "    up = basis + mult * dev\n"
        header += "    dn = basis - mult * dev\n"
        header += "    return up, basis, dn\n\n"
        final = header + code
        st.success("Converted " + vlabel)
        st.code(final, language="python")
        st.download_button(
            "Download .py", final,
            file_name="converted.py"
        )
        if df is not None and "close" in df.columns:
            st.subheader("📈 Backtest")
            close = df["close"]
            high = df["high"]
            low = df["low"]

            def RSI_fn(c, period=14):
                delta = c.diff()
                g = delta.where(delta > 0, 0)
                g = g.rolling(period).mean()
                l = -delta.where(delta < 0, 0)
                l = l.rolling(period).mean()
                rs = g / l
                return 100 - (100 / (1 + rs))

            def ATR_fn(h, l, c, period=14):
                a = h - l
                b = (h - c.shift(1)).abs()
                cc = (l - c.shift(1)).abs()
                tr = pd.concat([a, b, cc], axis=1).max(axis=1)
                return tr.rolling(period).mean()

            def MACD_fn(c, fast=12, slow=26, sig=9):
                ef = c.ewm(span=fast).mean()
                es = c.ewm(span=slow).mean()
                m = ef - es
                s = m.ewm(span=sig).mean()
                return m, s, m - s

            def BB_fn(c, period=20, mult=2):
                basis = c.rolling(period).mean()
                dev = c.rolling(period).std()
                up = basis + mult * dev
                dn = basis - mult * dev
                return up, basis, dn

            env = {}
            env["pd"] = pd
            env["np"] = np
            env["close"] = close
            env["high"] = high
            env["low"] = low
            env["LONG"] = 1
            env["SHORT"] = -1
            env["RSI"] = RSI_fn
            env["ATR"] = ATR_fn
            env["MACD"] = MACD_fn
            env["BB"] = BB_fn
            exec(code, env)
            sig_series = None
            if "longCondition" in env:
                if "shortCondition" in env:
                    lc = env["longCondition"].fillna(False)
                    sc = env["shortCondition"].fillna(False)
                    sig_series = np.where(lc, 1, 0)
                    sig_series = np.where(sc, -1, sig_series)
            elif "rsi" in env:
                rv = env["rsi"]
                sig_series = np.where(rv < 30, 1, 0)
                sig_series = np.where(rv > 70, -1, sig_series)
            if sig_series is not None:
                pos = pd.Series(sig_series, index=df.index)
                pos = pos.replace(0, np.nan)
                pos = pos.ffill().fillna(0)
                pos = pos.clip(lower=0)
                rets = close.pct_change().fillna(0)
                srets = pos.shift(1).fillna(0) * rets
                eq = (1 + srets).cumprod() * 10000
                bh = (1 + rets).cumprod() * 10000
                tr_ret = (eq.iloc[-1] / 10000 - 1) * 100
                bh_ret = (bh.iloc[-1] / 10000 - 1) * 100
                trades = int((pos.diff() != 0).sum())
                nz = srets[srets != 0]
                if len(nz) > 0:
                    wr = float((nz > 0).mean() * 100)
                else:
                    wr = 0
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Strategy", f"{tr_ret:.2f}%")
                m2.metric("Buy Hold", f"{bh_ret:.2f}%")
                m3.metric("Trades", trades)
                m4.metric("Win Rate", f"{wr:.1f}%")
                cdf = pd.DataFrame(
                    {"Strategy": eq, "Buy Hold": bh}
                )
                st.line_chart(cdf)
            else:
                st.info("No signal found")
        else:
            st.info("Load data first")