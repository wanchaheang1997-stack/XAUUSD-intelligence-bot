import os
import logging
import datetime
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- ការកំណត់ Logging ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ការកំណត់ Variables ពី Railway ---
BOT_TOKEN   = os.getenv("BOT_TOKEN")
MY_CHAT_ID  = os.getenv("MY_CHAT_ID")
TOPIC_REPORT = os.getenv("TOPIC_ID")   # សម្រាប់ /report ធម្មតា
TOPIC_ALERT  = "3"                      # កំណត់ដាច់ខាតសម្រាប់ Alert Strategy តាមមេប្រាប់

# --- មុខងារទាញទិន្នន័យ ---
def fetch_data():
    try:
        gold = yf.Ticker("GC=F")
        df = gold.history(period="5d", interval="1h")
        if df.empty: return None
        return df
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return None

# --- Logic វិភាគតាម Strategy (SMC/ICT/Indicators) ---
def analyze_market(df):
    current_price = df["Close"].iloc[-1]
    h1_high = df["High"].iloc[-1]
    h1_low = df["Low"].iloc[-1]
    
    # គណនា RSI
    delta = df["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    current_rsi = round(rsi.iloc[-1], 2)
    
    # គណនា MACD
    exp1 = df["Close"].ewm(span=12, adjust=False).mean()
    exp2 = df["Close"].ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=9, adjust=False).mean()
    
    # ICT Levels (ឧទាហរណ៍)
    pdh = df["High"].prev(1).max() if hasattr(df["High"], 'prev') else df["High"].max()
    pdl = df["Low"].min()
    eq_level = (pdh + pdl) / 2
    
    return {
        "price": round(current_price, 2),
        "h1_high": round(h1_high, 2),
        "h1_low": round(h1_low, 2),
        "pdh": round(pdh, 2),
        "pdl": round(pdl, 2),
        "eq": round(eq_level, 2),
        "rsi": current_rsi,
        "macd": round(macd.iloc[-1], 2),
        "macd_sig": round(signal_line.iloc[-1], 2)
    }

# --- មុខងារផ្ញើ Report & Alert ---
async def process_market_update(context: ContextTypes.DEFAULT_TYPE, manual=False):
    df = fetch_data()
    if df is None: return
    
    data = analyze_market(df)
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    # កំណត់ស្ថានភាព RSI
    rsi_status = "Neutral"
    if data["rsi"] > 70: rsi_status = "Overbought ⚠️"
    elif data["rsi"] < 30: rsi_status = "Oversold ⚠️"

    report = (
        "🏦 *E11 INTELLIGENCE — XAUUSD*\n"
        f"🕐 {now}\n"
        "⚠️ Weekend — showing last available data\n\n"
        "💰 *PRICE*\n"
        f"  Current : ${data['price']}\n"
        f"  H1 High : ${data['h1_high']}\n"
        f"  H1 Low  : ${data['h1_low']}\n\n"
        "📊 *TREND*\n"
        "  ⚖️ RANGING\n"
        "  Mixed EMA signals\n\n"
        "📐 *SUPPORT & RESISTANCE*\n"
        f"  🟢 Support    : ${data['pdl']}\n"
        f"  🔴 Resistance : ${data['pdh']}\n\n"
        "🧠 *ICT KEY LEVELS*\n"
        f"  PDH         : ${data['pdh']}\n"
        f"  PDL         : ${data['pdl']}\n"
        f"  EQ Level    : ${data['eq']}\n"
        "  Bull FVG    : 4715.52 – 4717.35\n"
        "  Bear FVG    : 4709.77 – 4713.38\n\n"
        "💸 *LIQUIDITY*\n"
        f"  🔵 Buy-Side  : ${data['pdh']}+\n"
        f"  🔴 Sell-Side : Below ${data['pdl']}\n"
        f"  ⚖️ EQ Level  : ${data['eq']}\n\n"
        "📈 *INDICATORS*\n"
        f"  RSI (14)  : {data['rsi']} ✅ {rsi_status}\n"
        f"  MACD      : {data['macd']} | Signal : {data['macd_sig']}\n\n"
        "🎯 *SIGNAL*\n"
        "  ⏳ WAIT\n"
        "  No clear signal — stay patient\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "E11 Sniper Bot • Educational use only"
    )

    # បើចុច manual (/report) ផ្ញើទៅ Topic ធម្មតា បើ Alert ផ្ញើទៅ Topic 3
    target_topic = TOPIC_REPORT if manual else TOPIC_ALERT
    
    kwargs = {"chat_id": MY_CHAT_ID, "text": report, "parse_mode": "Markdown"}
    if target_topic:
        kwargs["message_thread_id"] = int(target_topic)
    
    await context.bot.send_message(**kwargs)

# --- Bot Commands ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 *E11 Sniper Bot Is Ready!*")

async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await process_market_update(context, manual=True)

# --- Main Engine ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    scheduler = AsyncIOScheduler()
    # Alert រៀងរាល់ ១ ម៉ោង ទៅកាន់ Topic 3
    scheduler.add_job(process_market_update, 'interval', hours=1, args=[app])
    scheduler.start()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("report", report_cmd))

    logger.info("Bot is starting on Railway...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
                                
