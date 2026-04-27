import os
import logging
import datetime
import asyncio
import yfinance as yf
import pandas as pd
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.error import BadRequest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Config ---
BOT_TOKEN   = os.getenv("BOT_TOKEN")
MY_CHAT_ID  = os.getenv("MY_CHAT_ID")
TOPIC_ID    = os.getenv("TOPIC_ID")
ALERT_TOPIC = "3" 

# --- Market Analysis ---
async def get_market_analysis():
    try:
        gold = yf.Ticker("GC=F")
        df = gold.history(period="5d", interval="1h")
        if df.empty: return None

        price = round(df["Close"].iloc[-1], 2)
        high = round(df["High"].iloc[-1], 2)
        low = round(df["Low"].iloc[-1], 2)
        res = round(df["High"].max(), 2)
        sup = round(df["Low"].min(), 2)
        eq = round((res + sup) / 2, 2)

        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = round(100 - (100 / (1 + rs)).iloc[-1], 2)

        return {
            "price": price, "high": high, "low": low, 
            "res": res, "sup": sup, "eq": eq, "rsi": rsi
        }
    except Exception as e:
        logger.error(f"Analysis Error: {e}")
        return None

# --- Report Sender ---
async def send_full_report(context: ContextTypes.DEFAULT_TYPE, is_scheduled=False):
    data = await get_market_analysis()
    if not data: return

    # កែត្រង់នេះ៖ បន្ថែមសញ្ញា _ រវាង Phnom និង Penh
    kh_tz = pytz.timezone('Asia/Phnom_Penh')
    now_kh = datetime.datetime.now(kh_tz)
    time_str = now_kh.strftime("%Y-%m-%d %H:%M")
    
    status = "🟢 Market is Open" if now_kh.weekday() < 5 else "⚠️ Weekend (Last Close)"

    report = (
        "🏦 *E11 INTELLIGENCE — XAUUSD*\n"
        f"🕐 {time_str} (Cambodia Time)\n"
        f"{status}\n\n"
        "💰 *PRICE*\n"
        f"  Current : ${data['price']}\n"
        f"  H1 High : ${data['high']}\n"
        f"  H1 Low  : ${data['low']}\n\n"
        "📊 *TREND*\n"
        "  ⚖️ RANGING\n\n"
        "📐 *SUPPORT & RESISTANCE*\n"
        f"  🟢 Support    : ${data['sup']}\n"
        f"  🔴 Resistance : ${data['res']}\n\n"
        "🧠 *ICT KEY LEVELS*\n"
        f"  EQ Level    : ${data['eq']}\n\n"
        "📈 *INDICATORS*\n"
        f"  RSI (14)  : {data['rsi']} ✅\n\n"
        "🎯 *SIGNAL*\n"
        "  ⏳ WAIT\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "E11 Sniper Bot • Live Data"
    )

    target_topic = ALERT_TOPIC if is_scheduled else TOPIC_ID
    
    try:
        await context.bot.send_message(
            chat_id=MY_CHAT_ID,
            text=report,
            message_thread_id=target_topic,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Send Error: {e}")

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 E11 Sniper Bot ដើរហើយមេ!")

async def manual_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_full_report(context, is_scheduled=False)

# --- Main ---
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # កែត្រង់នេះដែរ៖ បន្ថែមសញ្ញា _
    kh_tz = pytz.timezone('Asia/Phnom_Penh')
    scheduler = AsyncIOScheduler(timezone=kh_tz)

    for hr in [8, 14, 19]:
        scheduler.add_job(
            send_full_report, 
            'cron', 
            hour=hr, 
            minute=0, 
            args=[app],
            name=f"Job_At_{hr}"
        )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", manual_report))

    async with app:
        await app.initialize()
        await app.start()
        
        if not scheduler.running:
            scheduler.start()
            
        logger.info("✅ Bot & Scheduler Started (Asia/Phnom_Penh)")
        await app.updater.start_polling(drop_pending_updates=True)
        
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            await app.stop()
            scheduler.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Bot Crashed: {e}")
    
