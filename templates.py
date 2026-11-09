"""Starter strategies offered in the Strategies tab. Each one is plain Python you can edit."""

TREND_PULLBACK = '''\
# Trend Pullback: buy dips to the fast EMA in an uptrend, sell rallies in a downtrend.
# signals() looks at each CLOSED bar. A trade enters at the NEXT bar's open.

PARAMS = {
    "trend_len": {"default": 100, "min": 20, "max": 400, "step": 10, "grid": [50, 100, 200]},
    "fast_len":  {"default": 20,  "min": 5,  "max": 100, "grid": [10, 20, 30]},
    "sl_atr":    {"default": 1.5, "min": 0.3, "max": 6, "step": 0.1, "grid": [1.0, 1.5, 2.0]},
    "rr":        {"default": 2.0, "min": 0.5, "max": 10, "step": 0.1, "grid": [1.5, 2.0, 3.0]},
}
MAX_HOLD = 48   # close the trade at market after this many bars
WARMUP = 250    # skip the first bars while indicators settle


def valid(p):   # optional: skip setting combinations that make no sense
    return p["fast_len"] < p["trend_len"]


def signals(df, p):
    o, h, l, c = df["open"], df["high"], df["low"], df["close"]
    trend, fast, a = ema(c, p["trend_len"]), ema(c, p["fast_len"]), atr(df, 14)
    buy = (c > trend) & (fast > trend) & (l <= fast) & (c > fast) & (c > o)
    sell = (c < trend) & (fast < trend) & (h >= fast) & (c < fast) & (c < o)
    stop = p["sl_atr"] * a                       # stop distance in price units
    return {"side": buy.astype(int) - sell.astype(int), "sl": stop, "tp": stop * p["rr"]}


def plots(df, p):   # optional: lines drawn on the Visual chart
    return {"EMA trend": ema(df["close"], p["trend_len"]), "EMA fast": ema(df["close"], p["fast_len"])}
'''

RSI_REVERSION = '''\
# RSI Mean Reversion: buy when RSI recovers from oversold inside an uptrend,
# sell when it falls back from overbought inside a downtrend.

PARAMS = {
    "rsi_len":   {"default": 14, "min": 2, "max": 50, "grid": [7, 14, 21]},
    "oversold":  {"default": 30, "min": 5, "max": 45, "grid": [20, 30]},
    "trend_len": {"default": 200, "min": 50, "max": 400, "step": 10, "grid": [100, 200]},
    "sl_atr":    {"default": 2.0, "min": 0.5, "max": 6, "step": 0.1, "grid": [1.5, 2.0, 3.0]},
    "rr":        {"default": 1.0, "min": 0.5, "max": 5, "step": 0.1, "grid": [1.0, 1.5]},
}
MAX_HOLD = 24
WARMUP = 250


def signals(df, p):
    c = df["close"]
    r, trend, a = rsi(c, p["rsi_len"]), sma(c, p["trend_len"]), atr(df, 14)
    buy = crossover(r, p["oversold"]) & (c > trend)
    sell = crossunder(r, 100 - p["oversold"]) & (c < trend)
    stop = p["sl_atr"] * a
    return {"side": buy.astype(int) - sell.astype(int), "sl": stop, "tp": stop * p["rr"]}


def plots(df, p):
    return {"SMA trend": sma(df["close"], p["trend_len"])}
'''

DONCHIAN = '''\
# Donchian Breakout: buy a new N-bar high, sell a new N-bar low.
# No fixed target (tp = 0): trades end on the stop or after MAX_HOLD bars.

PARAMS = {
    "length": {"default": 55, "min": 10, "max": 300, "step": 5, "grid": [20, 55, 100]},
    "sl_atr": {"default": 2.0, "min": 0.5, "max": 8, "step": 0.1, "grid": [1.5, 2.0, 3.0]},
}
MAX_HOLD = 60
WARMUP = 150


def signals(df, p):
    c = df["close"]
    top = highest(df["high"], p["length"]).shift(1)     # shift(1) = only bars BEFORE this one
    bottom = lowest(df["low"], p["length"]).shift(1)
    buy, sell = c > top, c < bottom
    return {"side": buy.astype(int) - sell.astype(int), "sl": p["sl_atr"] * atr(df, 14), "tp": 0}


def plots(df, p):
    return {"Upper": highest(df["high"], p["length"]).shift(1), "Lower": lowest(df["low"], p["length"]).shift(1)}
'''

BLANK = '''\
# Your own strategy. Open "How to write a strategy" under the editor for the full guide.

PARAMS = {
    "length": {"default": 20, "min": 2, "max": 200, "grid": [10, 20, 40]},
    "sl_atr": {"default": 1.5, "min": 0.3, "max": 6, "step": 0.1, "grid": [1.0, 1.5, 2.0]},
}
MAX_HOLD = 48
WARMUP = 100


def signals(df, p):
    c = df["close"]
    mid = sma(c, p["length"])
    buy = crossover(c, mid)         # price crosses above its average
    sell = crossunder(c, mid)       # price crosses below it
    return {"side": buy.astype(int) - sell.astype(int),   # +1 buy, -1 sell, 0 nothing
            "sl": p["sl_atr"] * atr(df, 14),              # stop distance in price units
            "tp": 0}                                      # 0 = no fixed target


def plots(df, p):
    return {"SMA": sma(df["close"], p["length"])}
'''

TEMPLATES = [
    {"key": "trend_pullback", "name": "Trend Pullback (EMA)", "code": TREND_PULLBACK},
    {"key": "rsi_reversion", "name": "RSI Mean Reversion", "code": RSI_REVERSION},
    {"key": "donchian", "name": "Donchian Breakout", "code": DONCHIAN},
    {"key": "blank", "name": "Blank (start from scratch)", "code": BLANK},
]