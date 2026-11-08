import streamlit as st
import re

st.set_page_config(page_title="PineToPy", page_icon="🌲")
st.title("🌲 PineToPy - Pine to Python")
st.write("Paste Pine Script, get working Python with pandas.")

pine_code = st.text_area("Paste Pine Script here:", height=300, placeholder="//@version=5\nindicator(...)")

if st.button("Convert to Python"):
    if not pine_code.strip():
        st.warning("Please paste some Pine Script first.")
    else:
        code = pine_code

        # Basic conversions
        code = code.replace("ta.sma(close,", "close.rolling(window=")
        code = code.replace("ta.ema(close,", "close.ewm(span=")
        code = code.replace("ta.rsi(close,", "RSI_PLACEHOLDER(")

        # Fix rolling - add .mean() - handles space like window= 9
        code = re.sub(r'close\.rolling\(window=\s*(\d+)\)', r'close.rolling(window=\1).mean()', code)
        code = re.sub(r'close\.ewm\(span=\s*(\d+)\)', r'close.ewm(span=\1, adjust=False).mean()', code)

        # indicator -> comment
        code = re.sub(r'indicator\(.*?\)', '# Indicator', code)
        code = re.sub(r'//@version=.*', '# Pine Script v5', code)

        # plot -> comment
        code = re.sub(r'plot\(.*\)', lambda m: f"# plot: {m.group(0)}", code)

        # crossover / crossunder -> pandas logic
        code = code.replace("ta.crossover(fast, slow)", "(fast > slow) & (fast.shift(1) <= slow.shift(1))")
        code = code.replace("ta.crossunder(fast, slow)", "(fast < slow) & (fast.shift(1) >= slow.shift(1))")
        code = code.replace("ta.crossover(", "(crossover ")
        code = code.replace("ta.crossunder(", "(crossunder ")

        # strategy.entry -> signal
        code = code.replace('strategy.entry("Long", strategy.long)', 'signal = "BUY"')
        code = code.replace('strategy.entry("Short", strategy.short)', 'signal = "SELL"')
        code = code.replace("strategy.entry", "# strategy.entry")
        code = code.replace("strategy.long", '"LONG"')
        code = code.replace("strategy.short", '"SHORT"')

        # true/false
        code = code.replace("true", "True").replace("false", "False")
        # color.blue etc
        code = re