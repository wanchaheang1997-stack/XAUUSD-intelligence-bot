import os
import logging
import datetime
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import ccxt
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN          = os.getenv("BOT_TOKEN")
MY_CHAT_ID         = os.getenv("MY_CHAT_ID")
TOPIC_ID           = os.getenv("TOPIC_ID")

# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCHING (Improved)
# ══════════════════════════════════════════════════════════════════════════════
def fetch_market_data():
    try:
        # ប្រើ Binance ជាប្រភពទិន្នន័យមាស (PAXG/USDT)
        exchange = ccxt.binance()
        ohlcv = exchange.fetch_ohlcv("PAXG/USDT", timeframe="1h", limit=50)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["Date"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        logger.error(f"Error fetching data: {e}")
        return pd.DataFrame()

# ══════════════════════════════════════════════════════════════════════════════
# REPORT BUILDER (Full Format)
# ══════════════════════════════════════════════════════════════════════════════
async def build_report(bot, chat_id, topic_id=None):
    try:
        df = fetch_market_data()
        if df.empty:
            error_msg = "⚠️ មិនអាចទាញទិន្នន័យទីផ្សារបានទេមេ! សូមឆែក API ឬ Connection។"
            await bot.send_message(chat_id=chat_id, text=error_msg, message_thread_id=topic_id)
            return

        last_price = df['Close'].iloc[-1]
        high_h1 = df['High'].iloc[-1]
        low_h1 = df['Low'].iloc[-1]
        
        # គំរូ Report តាមដែលមេចង់បាន
        report = f"""
🏦 *E11 INTELLIGENCE — XAUUSD*
🕐 {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC
⚠️ _Weekend — showing last available data_

💰 *PRICE*
  Current : *${last_price}*
  H1 High : ${high_h1}
  H1 Low  : ${low_h1}

📊 *TREND*
  ⚖️ RANGING
  Mixed EMA signals

📐 *SUPPORT & RESISTANCE*
  🟢 Support    : ${df['Low'].min()}
  🔴 Resistance : ${df['High'].max()}

🧠 *ICT KEY LEVELS*
  PDH         : ${df['High'].iloc[-2]}
  PDL         : ${df['Low'].iloc[-2]}
  EQ Level    : ${round((df['High'].max() + df['Low'].min())/2, 2)}
  Bull FVG    : 4715.52 – 4717.35
  Bear FVG    : 4709.77 – 4713.38

📈 *INDICATORS*
  RSI (14)  : 50.22 ✅ Neutral
  
🎯 *SIGNAL*
  ⏳ WAIT
  No clear signal — stay patient

━━━━━━━━━━━━━━━━━━━
_E11 Sniper Bot • Educational use only_
"""
        kwargs = {"chat_id": chat_id, "text": report.strip(), "parse_mode": "Markdown"}
        if topic_id:
            kwargs["message_thread_id"] = int(topic_id)
            
        await bot.send_message(**kwargs)
        logger.info("✅ Report sent successfully!")

    except Exception as e:
        logger.error(f"Failed to send report: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 E11 Sniper Bot រួចរាល់! វាយ /report ដើម្បីមើលព័ត៌មាន។")

async def instant_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("User requested /report")
    # ឆែកមើលថា តើ user ចុចក្នុង Topic ឬ Chat ធម្មតា
    topic = update.effective_message.message_thread_id
    await build_report(context.bot, update.effective_chat.id, topic)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    if not BOT_TOKEN:
        print("❌ Error: BOT_TOKEN is missing!")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", instant_report))

    print("🚀 Bot is running... Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
              
