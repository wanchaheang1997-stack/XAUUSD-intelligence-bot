import os
import logging
import datetime
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import ccxt
import time
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN          = os.getenv("BOT_TOKEN")
MY_CHAT_ID         = os.getenv("MY_CHAT_ID")
TOPIC_ID           = os.getenv("TOPIC_ID")
TOPIC_ALERT        = os.getenv("TOPIC_ALERT")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")

last_alert_time = {}

# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCHING
# ══════════════════════════════════════════════════════════════════════════════

def get_exchange():
    return ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })

def fetch_ohlcv(timeframe="1h", limit=200):
    try:
        exchange = get_exchange()
        ohlcv    = exchange.fetch_ohlcv("PAXG/USDT", timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["Date"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        logger.warning(f"ccxt failed ({e}) — falling back to Twelve Data")
        return fetch_twelvedata(timeframe, limit)

def fetch_twelvedata(timeframe="1h", limit=200):
    interval_map = {"1m": "1min", "5m": "5min", "1h": "1h", "1d": "1day"}
    interval = interval_map.get(timeframe, "1h")
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol"    : "XAU/USD",
        "interval"  : interval,
        "outputsize": limit,
        "apikey"    : TWELVEDATA_API_KEY,
    }
    r    = requests.get(url, params=params, timeout=10)
    data = r.json()
    if "values" not in data:
        raise ValueError(f"Twelve Data error: {data.get('message', 'No data')}")
    df = pd.DataFrame(data["values"])
    df = df.rename(columns={
        "datetime": "Date", "open": "Open",
        "high": "High", "low": "Low", "close": "Close",
    })
    df["Date"]   = pd.to_datetime(df["Date"])
    df["Open"]   = df["Open"].astype(float)
    df["High"]   = df["High"].astype(float)
    df["Low"]    = df["Low"].astype(float)
    df["Close"]  = df["Close"].astype(float)
    df["Volume"] = 0.0
    df = df.sort_values("Date").reset_index(drop=True)
    return df

def get_live_price():
    try:
        exchange = get_exchange()
        ticker   = exchange.fetch_ticker("PAXG/USDT")
        return round(float(ticker["last"]), 2)
    except Exception:
        try:
            url    = "https://api.twelvedata.com/price"
            params = {"symbol": "XAU/USD", "apikey": TWELVEDATA_API_KEY}
            r      = requests.get(url, params=params, timeout=10)
            data   = r.json()
            if "price" in data:
                return round(float(data["price"]), 2)
        except Exception:
            pass
    return None

# ══════════════════════════════════════════════════════════════════════════════
# INDICATORS & ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = -delta.clip(upper=0).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series):
    ema12     = series.ewm(span=12, adjust=False).mean()
    ema26     = series.ewm(span=26, adjust=False).mean()
    macd      = ema12 - ema26
    signal    = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return macd, signal, histogram

def get_trend(df):
    ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
    ema50 = df["Close"].ewm(span=50).mean().iloc[-1]
    price = df["Close"].iloc[-1]
    if price > ema20 > ema50:
        return "📈 BULLISH", "Price above EMA20 & EMA50"
    elif price < ema20 < ema50:
        return "📉 BEARISH", "Price below EMA20 & EMA50"
    else:
        return "⚖️ RANGING", "Mixed EMA signals"

def get_support_resistance(df):
    resistance = round(df["High"].rolling(10).max().iloc[-1], 2)
    support    = round(df["Low"].rolling(10).min().iloc[-1], 2)
    return support, resistance

def get_daily_levels():
    df  = fetch_ohlcv("1d", 5)
    pdh = round(df["High"].iloc[-2], 2)
    pdl = round(df["Low"].iloc[-2], 2)
    pdc = round(df["Close"].iloc[-2], 2)
    return pdh, pdl, pdc

def get_session_levels(df_1h):
    now   = datetime.datetime.utcnow()
    today = now.date()
    sessions = {"Asia": (0, 8), "London": (7, 16), "NY": (13, 22)}
    result = {}
    for session, (start_h, end_h) in sessions.items():
        mask = (df_1h["Date"].dt.date == today) & (df_1h["Date"].dt.hour >= start_h) & (df_1h["Date"].dt.hour < end_h)
        session_df = df_1h[mask]
        result[session] = {"high": round(session_df["High"].max(), 2) if not session_df.empty else None,
                           "low": round(session_df["Low"].min(), 2) if not session_df.empty else None}
    return result

def detect_bos_choch(df_1h):
    highs, lows = df_1h["High"].rolling(5).max(), df_1h["Low"].rolling(5).min()
    last_close, prev_high, prev_low = df_1h["Close"].iloc[-1], highs.iloc[-3], lows.iloc[-3]
    if last_close > prev_high: return "BOS_BULLISH", f"Price broke above ${round(prev_high, 2)}"
    if last_close < prev_low: return "BOS_BEARISH", f"Price broke below ${round(prev_low, 2)}"
    return "NONE", "No structure break"

def detect_fvg(df):
    fvg_bull, fvg_bear = None, None
    for i in range(2, len(df)):
        if df["Low"].iloc[i] > df["High"].iloc[i-2]: fvg_bull = (round(df["High"].iloc[i-2], 2), round(df["Low"].iloc[i], 2))
        if df["High"].iloc[i] < df["Low"].iloc[i-2]: fvg_bear = (round(df["High"].iloc[i], 2), round(df["Low"].iloc[i-2], 2))
    return fvg_bull, fvg_bear

def detect_order_block(df):
    ob_bull, ob_bear = None, None
    for i in range(1, len(df) - 1):
        curr, next_c = df.iloc[i], df.iloc[i + 1]
        if curr["Close"] < curr["Open"] and next_c["Close"] > next_c["Open"] and abs(next_c["Close"]-next_c["Open"]) > abs(curr["Close"]-curr["Open"]) * 1.5:
            ob_bull = (round(curr["Low"], 2), round(curr["High"], 2))
        if curr["Close"] > curr["Open"] and next_c["Close"] < next_c["Open"] and abs(next_c["Close"]-next_c["Open"]) > abs(curr["Close"]-curr["Open"]) * 1.5:
            ob_bear = (round(curr["Low"], 2), round(curr["High"], 2))
    return ob_bull, ob_bear

def get_volume_profile(df):
    poc = round(df["Close"].median(), 2)
    vah = round(df["High"].quantile(0.75), 2)
    val = round(df["Low"].quantile(0.25), 2)
    return poc, vah, val

def get_economic_news():
    try:
        r = requests.get("https://www.fxstreet.com/rss/news", timeout=6)
        root = ET.fromstring(r.content)
        return [item.findtext("title") for item in root.iter("item")][:4]
    except: return ["No gold-related news found"]

# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL & REPORT HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

async def smc_signal_check(context: ContextTypes.DEFAULT_TYPE):
    global last_alert_time
    bot = context.bot
    try:
        price = get_live_price()
        if not price or datetime.datetime.utcnow().weekday() >= 5: return
        
        df_1h, df_5m = fetch_ohlcv("1h", 100), fetch_ohlcv("5m", 50)
        pdh, pdl, _ = get_daily_levels()
        poc, _, _ = get_volume_profile(df_1h)
        rsi = calculate_rsi(df_1h["Close"]).iloc[-1]
        
        signal = "BUY" if price > poc and rsi < 60 else "SELL" if price < poc and rsi > 40 else None
        if not signal: return

        now = datetime.datetime.utcnow()
        if signal in last_alert_time and (now - last_alert_time[signal]).seconds < 3600: return
        last_alert_time[signal] = now

        msg = f"⚡ *E11 SMC SIGNAL ALERT*\n\n{'🟢' if signal=='BUY' else '🔴'} *{signal} — XAUUSD*\nPrice: *${price}*\nStrategy: SMC Alignment"
        kwargs = {"chat_id": MY_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
        if TOPIC_ALERT: kwargs["message_thread_id"] = int(TOPIC_ALERT)
        await bot.send_message(**kwargs)
    except Exception as e: logger.error(f"Signal Error: {e}")

async def build_report(bot, chat_id, topic_id=None):
    try:
        df_1h = fetch_ohlcv("1h", 100)
        price = get_live_price() or df_1h["Close"].iloc[-1]
        msg = f"🏦 *E11 INTELLIGENCE — XAUUSD*\nPrice: *${price}*\nTrend: {get_trend(df_1h)[0]}"
        kwargs = {"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}
        if topic_id: kwargs["message_thread_id"] = int(topic_id)
        await bot.send_message(**kwargs)
    except Exception as e: logger.error(f"Report Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 *E11 Sniper Bot is live!*", parse_mode="Markdown")

async def instant_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await build_report(context.bot, update.effective_chat.id, update.effective_message.message_thread_id)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def main():
    if not BOT_TOKEN: return
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", instant_report))

    scheduler = AsyncIOScheduler()
    scheduler.add_job(smc_signal_check, 'interval', minutes=1, args=[app])
    scheduler.start()

    logger.info("🚀 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
