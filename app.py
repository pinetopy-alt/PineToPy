import re
import streamlit as st

st.set_page_config(page_title="PineToPy", page_icon="🌲", layout="centered")
st.title("🌲 PineToPy")
st.subheader("Paste Pine. Get Python.")

pine_code = st.text_area("Paste your Pine Script here:", height=250, placeholder="//@version=5\nindicator(\"My Strategy\")\nfast = ta.sma(close, 9)")

def convert_pine_to_python(code):
    python = code
    python = re.sub(r'//@version=\d+', '# Converted by PineToPy', python)
    python = re.sub(r'indicator\(".*?"\)', '# Indicator', python)
    python = re.sub(r'strategy\(".*?"\)', '# Strategy', python)
    python = python.replace('ta.sma(close, ', 'close.rolling(').replace('ta.ema(close, ', 'close.ewm(span=')
    python = re.sub(r'ta\.rsi\(close,\s*(\d+)\)', r'compute_rsi(close, \1)', python)
    python = re.sub(r'plot\((.*?),.*?\)', r'# plot: \1', python)
    python = re.sub(r'//(.*)', r'#\1', python)
    python = python.replace(':=', '=')
    python = python.replace('var ', '')
    python = python.replace('input.int', 'INPUT')
    python = python.replace('input.float', 'INPUT')
    python = python.replace('na', 'None')
    python = python.replace('true', 'True')
    python = python.replace('false', 'False')
    python = python.replace('and', 'and')
    python = python.replace('or', 'or')
    return python

if st.button("Convert to Python"):
    if pine_code.strip() == "":
        st.warning("Please paste some Pine Script first.")
    else:
        result = convert_pine_to_python(pine_code)
        st.code(result, language="python")
        st.success("Done! Copy your Python code above.")

st.markdown("---")
st.markdown("Made with PineToPy — Paste Pine. Get Python.")
