import os
import logging
import datetime
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import ccxt
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- កំណត់ការរៀបចំ Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# --- ទាញយកការកំណត់ពី Environment Variables (សម្រាប់ Railway) ---
BOT_TOKEN          = os.getenv("BOT_TOKEN")
MY_CHAT_ID         = os.getenv("MY_CHAT_ID")
TOPIC_ID           = os.getenv("TOPIC_ID")
TOPIC_ALERT        = os.getenv("TOPIC_ALERT")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")

last_alert_time = {}

# --- មុខងារទាញទិន្នន័យទីផ្សារ (Data Engines) ---
def fetch_ohlcv(timeframe="1h", limit=200):
    try:
        exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "spot"}})
        ohlcv = exchange.fetch_ohlcv("PAXG/USDT", timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["Date"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        logger.warning(f"Data Fetch Error: {e}")
        return None

def get_live_price():
    try:
        exchange = ccxt.binance()
        ticker = exchange.fetch_ticker("PAXG/USDT")
        return round(float(ticker["last"]), 2)
    except:
        return None

# --- មុខងារគណនាបច្ចេកទេស (Indicators) ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_volume_profile(df):
    poc = round(df["Close"].median(), 2)
    vah = round(df["High"].quantile(0.75), 2)
    val = round(df["Low"].quantile(0.25), 2)
    return poc, vah, val

# --- មុខងារវិភាគ SMC/ICT Concepts ---
def detect_fvg(df):
    fvg_bull, fvg_bear = None, None
    for i in range(2, len(df)):
        if df["Low"].iloc[i] > df["High"].iloc[i-2]:
            fvg_bull = (round(df["High"].iloc[i-2], 2), round(df["Low"].iloc[i], 2))
        if df["High"].iloc[i] < df["Low"].iloc[i-2]:
            fvg_bear = (round(df["High"].iloc[i], 2), round(df["Low"].iloc[i-2], 2))
    return fvg_bull, fvg_bear

# --- មុខងារចម្បងសម្រាប់ផ្ញើរបាយការណ៍ (Report Builder) ---
async def build_report(bot, chat_id, topic_id=None):
    df = fetch_ohlcv("1h", 100)
    if df is None: return
    
    price = get_live_price() or df["Close"].iloc[-1]
    rsi = round(calculate_rsi(df["Close"]).iloc[-1], 2)
    poc, vah, val = get_volume_profile(df)
    fvg_bull, fvg_bear = detect_fvg(df)
    
    report = (
        "🏦 *E11 INTELLIGENCE — XAUUSD*\n"
        f"🕐 {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        "💰 *PRICE*\n"
        f"  Current : *${price}*\n\n"
        "📊 *VOLUME PROFILE*\n"
        f"  POC : ${poc} | VAH : ${vah} | VAL : ${val}\n\n"
        "🧠 *ICT CONCEPTS*\n"
        f"  Bull FVG : {fvg_bull if fvg_bull else 'None'}\n"
        f"  Bear FVG : {fvg_bear if fvg_bear else 'None'}\n\n"
        "📈 *INDICATORS*\n"
        f"  RSI (14) : {rsi}\n\n"
        "🎯 *SIGNAL*\n"
        "  ⏳ WAIT — Stay patient\n\n"
        "---\n"
        "_E11 Sniper Bot • Educational use only_"
    )
    
    kwargs = {"chat_id": chat_id, "text": report, "parse_mode": "Markdown"}
    if topic_id: kwargs["message_thread_id"] = int(topic_id)
    await bot.send_message(**kwargs)

# --- Commands & Scheduling ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 *E11 Sniper Intelligence is Live!* Use /report", parse_mode="Markdown")

async def instant_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await build_report(context.bot, update.effective_chat.id, TOPIC_ID)

def main():
    if not BOT_TOKEN: raise EnvironmentError("BOT_TOKEN is missing!")
    
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # កំណត់ឱ្យផ្ញើ Report ស្វ័យប្រវត្តិតាមម៉ោង (ឧទាហរណ៍៖ រាល់ ១ ម៉ោង)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(lambda: build_report(app.bot, MY_CHAT_ID, TOPIC_ID), 'interval', hours=1)
    scheduler.start()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", instant_report))
    
    print("🚀 E11 Sniper Bot is deploying on Railway...")
    app.run_polling()

if __name__ == "__main__":
    main()
    
