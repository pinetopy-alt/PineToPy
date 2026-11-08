import streamlit as st
import re

st.set_page_config(page_title="PineToPy", page_icon="🌲")
st.title("🌲 PineToPy - Pine v5 & v6 to Python")
st.write("Paste Pine Script v5 or v6, get working Python with pandas.")

pine_code = st.text_area("Paste Pine Script here:", height=300, placeholder="//@version=6\nindicator(...)")

if st.button("Convert to Python"):
    if not pine_code.strip():
        st.warning("Please paste some Pine Script first.")
    else:
        code = pine_code
        is_v6 = "@version=6" in code
        version_label = "Pine Script v6" if is_v6 else "Pine Script v5"

        # --- Version header ---
        code = re.sub(r'//@version=.*', f'# {version_label}', code)

        # --- indicator / strategy ---
        code = re.sub(r'indicator\(.*?\)', '# Indicator', code)
        code = re.sub(r'strategy\(.*?\)', '# Strategy', code)
        code = re.sub(r'library\(.*?\)', '# Library', code)

        # --- Inputs (v5 + v6) ---
        # input.int(14, "Length") -> 14
        code = re.sub(r'input\.int\(\s*(\d+).*?\)', r'\1', code)
        code = re.sub(r'input\.float\(\s*([\d\.]+).*?\)', r'\1', code)
        code = re.sub(r'input\.bool\(\s*(true|false).*?\)', lambda m: "True" if m.group(1)=="true" else "False", code)
        code = re.sub(r'input\.string\(\s*"(.*?)".*?\)', r'"\1"', code)
        code = re.sub(r'input\.source\(\s*(close).*?\)', r'\1', code)

        # --- TA functions -> pandas ---
        code = code.replace("ta.sma(close,", "close.rolling(window=")
        code = code.replace("ta.ema(close,", "close.ewm(span=")
        code = code.replace("ta.wma(close,", "close.rolling(window=")
        code = code.replace("ta.rma(close,", "close.ewm(alpha=1/")
        # rsi placeholder - real RSI calc added in header comment
        code = re.sub(r'ta\.rsi\(close,\s*(\d+)\)', r'RSI(close, \1)', code)
        code = re.sub(r'ta\.atr\(\s*(\d+)\)', r'ATR(high, low, close, \1)', code)
        code = re.sub(r'ta\.macd\(close,\s*(\d+),\s*(\d+),\s*(\d+)\)', r'MACD(close, \1, \2, \3)', code)
        code = re.sub(r'ta\.stoch\(close,\s*high,\s*low,\s*(\d+)\)', r'STOCH(close, high, low, \1)', code)
        code = re.sub(r'ta\.bb\(close,\s*(\d+),\s*(\d+)\)', r'BB(close, \1, \2)', code)
        code = re.sub(r'ta\.highest\(close,\s*(\d+)\)', r'close.rolling(window=\1).max()', code)
        code = re.sub(r'ta\.lowest\(close,\s*(\d+)\)', r'close.rolling(window=\1).min()', code)
        code = re.sub(r'ta\.change\(close\)', r'close.diff()', code)
        code = re.sub(r'ta\.mom\(close,\s*(\d+)\)', r'close.diff(\1)', code)

        # Fix rolling / ewm - handles window= 9 and window=9
        code = re.sub(r'close\.rolling\(window=\s*(\d+)\)', r'close.rolling(window=\1).mean()', code)
        code = re.sub(r'close\.ewm\(span=\s*(\d+)\)', r'close.ewm(span=\1, adjust=False).mean()', code)
        code = re.sub(r'close\.ewm\(alpha=1/\s*(\d+)\)', r'close.ewm(alpha=1/\1, adjust=False).mean()', code)

        # --- request.security (v6) ---
        code = re.sub(r'request\.security\(.*?,\s*"(.*?)",\s*(.*?)\)', r'# request.security -> use \2 from \1', code)
        code = re.sub(r'request\.security\(.*?\)', '# request.security - load data separately', code)

        # --- plot / plotshape / hline ---
        code = re.sub(r'plot\(.*\)', lambda m: f"# plot: {m.group(0)}", code)
        code = re.sub(r'plotshape\(.*\)', lambda m: f"# plotshape: {m.group(0)}", code)
        code = re.sub(r'hline\(.*\)', lambda m: f"# hline: {m.group(0)}", code)
        code = re.sub(r'bgcolor\(.*\)', lambda m: f"# bgcolor: {m.group(0)}", code)

        # --- crossover / crossunder ---
        code = code.replace("ta.crossover(fast, slow)", "(fast > slow) & (fast.shift(1) <= slow.shift(1))")
        code = code.replace("ta.crossunder(fast, slow)", "(fast < slow) & (fast.shift(1) >= slow.shift(1))")
        code = re.sub(r'ta\.crossover\((.*?),\s*(.*?)\)', r'(\1 > \2) & (\1.shift(1) <= \2.shift(1))', code)
        code = re.sub(r'ta\.crossunder\((.*?),\s*(.*?)\)', r'(\1 < \2) & (\1.shift(1) >= \2.shift(1))', code)
        code = code.replace("ta.crossover(", "(crossover ")
        code = code.replace("ta.crossunder(", "(crossunder ")

        # --- strategy.* (v5 + v6) ---
        code = code.replace('strategy.entry("Long", strategy.long)', 'signal = "BUY"')
        code = code.replace('strategy.entry("Short", strategy.short)', 'signal = "SELL"')
        code = re.sub(r'strategy\.entry\(".*?",\s*strategy\.long\)', 'signal = "BUY"', code)
        code = re.sub(r'strategy\.entry\(".*?",\s*strategy.short