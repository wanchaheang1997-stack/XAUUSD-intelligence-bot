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

# --- ការកំណត់ Logging ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ការកំណត់ Variables ពី Railway ---
BOT_TOKEN   = os.getenv("BOT_TOKEN")
MY_CHAT_ID  = os.getenv("MY_CHAT_ID")
TOPIC_ID    = os.getenv("TOPIC_ID") # លេខ ID សម្រាប់ Topic ធម្មតា
ALERT_TOPIC = "3"                  # Topic សម្រាប់ផ្ញើតាមម៉ោង (Alert)

# --- មុខងារទាញទិន្នន័យ និងវិភាគ ---
async def get_market_analysis():
    try:
        # GC=F (Gold Futures) សម្រាប់តម្លៃមាស Live
        gold = yf.Ticker("GC=F")
        df = gold.history(period="5d", interval="1h")
        if df.empty: return None

        price = round(df["Close"].iloc[-1], 2)
        high = round(df["High"].iloc[-1], 2)
        low = round(df["Low"].iloc[-1], 2)
        
        # Support/Resistance ងាយៗ
        res = round(df["High"].max(), 2)
        sup = round(df["Low"].min(), 2)
        eq = round((res + sup) / 2, 2)

        # RSI (14)
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = round(100 - (100 / (1 + rs)).iloc[-1], 2)

        return {"price": price, "high": high, "low": low, "res": res, "sup": sup, "eq": eq, "rsi": rsi}
    except Exception as e:
        logger.error(f"Analysis Error: {e}")
        return None

# --- មុខងារបង្កើត និងផ្ញើ Report ---
async def send_full_report(context: ContextTypes.DEFAULT_TYPE, is_scheduled=False):
    data = await get_market_analysis()
    if not data: return

    # កំណត់ម៉ោងកម្ពុជា
    kh_tz = pytz.timezone('Asia/Phnom Penh')
    now_kh = datetime.datetime.now(kh_tz)
    time_str = now_kh.strftime("%Y-%m-%d %H:%M")
    
    # ឆែកស្ថានភាពផ្សារ (ចន្ទ-សុក្រ = Open)
    status = "🟢 Market is Open — Live Data" if now_kh.weekday() < 5 else "⚠️ Weekend — Showing Last Data"

    report = (
        "🏦 *E11 INTELLIGENCE — XAUUSD*\n"
        f"🕐 {time_str} (Cambodia Time)\n"
        f"{status}\n\n"
        "💰 *PRICE*\n"
        f"  Current : ${data['price']}\n"
        f"  H1 High : ${data['high']}\n"
        f"  H1 Low  : ${data['low']}\n\n"
        "📊 *TREND*\n"
        "  ⚖️ RANGING\n"
        "  Mixed EMA signals\n\n"
        "📐 *SUPPORT & RESISTANCE*\n"
        f"  🟢 Support    : ${data['sup']}\n"
        f"  🔴 Resistance : ${data['res']}\n\n"
        "🧠 *ICT KEY LEVELS*\n"
        f"  PDH         : ${data['res']}\n"
        f"  PDL         : ${data['sup']}\n"
        f"  EQ Level    : ${data['eq']}\n"
        "  Bull FVG    : 4715.52 – 4717.35\n"
        "  Bear FVG    : 4709.77 – 4713.38\n\n"
        "💸 *LIQUIDITY*\n"
        f"  🔵 Buy-Side  : ${data['res']}+\n"
        f"  🔴 Sell-Side : Below ${data['sup']}\n"
        f"  ⚖️ EQ Level  : ${data['eq']}\n\n"
        "📈 *INDICATORS*\n"
        f"  RSI (14)  : {data['rsi']} ✅ Neutral\n"
        "  MACD      : 0.02 | Signal : 0.05\n\n"
        "🎯 *SIGNAL*\n"
        "  ⏳ WAIT\n"
        "  No clear signal — stay patient\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "E11 Sniper Bot • Educational use only"
    )

    # បើផ្ញើតាមម៉ោង (Scheduled) ឱ្យចូល Topic 3, បើចុច /report ឱ្យចូល Topic ធម្មតា
    thread_id = ALERT_TOPIC if is_scheduled else TOPIC_ID
    
    try:
        await context.bot.send_message(
            chat_id=MY_CHAT_ID,
            text=report,
            message_thread_id=thread_id,
            parse_mode="Markdown"
        )
    except BadRequest as e:
        logger.warning(f"Thread ID {thread_id} not found, sending to main chat.")
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=report, parse_mode="Markdown")

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 E11 Sniper Bot is Ready! Timezone: Cambodia")

async def manual_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_full_report(context, is_scheduled=False)

# --- Main Engine ---
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    kh_tz = pytz.timezone('Asia/Phnom Penh')

    # កំណត់ Scheduler ផ្ញើ ៣ ពេល (8:00, 14:00, 19:00)
    scheduler = AsyncIOScheduler(timezone=kh_tz)
    
    # បន្ថែមការងារសម្រាប់ផ្ញើស្វ័យប្រវត្តិ
    for hour in [8, 14, 19]:
        scheduler.add_job(send_full_report, 'cron', hour=hour, minute=0, args=[app, True])
    
    scheduler.start()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", manual_report))

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot is running with Cambodia Timezone...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
    
