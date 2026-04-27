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

# --- កំណត់ការបង្ហាញព័ត៌មានក្នុង Log ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ទាញយកតម្លៃពី Environment Variables ---
BOT_TOKEN   = os.getenv("BOT_TOKEN")
MY_CHAT_ID  = os.getenv("MY_CHAT_ID")
TOPIC_ID    = os.getenv("TOPIC_ID")
ALERT_TOPIC = "3"  # Topic សម្រាប់របាយការណ៍ស្វ័យប្រវត្តិ

# --- Function វិភាគទីផ្សារ (Advanced ICT & Indicators) ---
async def get_market_analysis():
    try:
        gold = yf.Ticker("GC=F")
        df = gold.history(period="10d", interval="1h")
        if df.empty: return None

        # តម្លៃបច្ចុប្បន្ន
        price = round(df["Close"].iloc[-1], 4)
        high_h1 = round(df["High"].iloc[-1], 4)
        low_h1 = round(df["Low"].iloc[-1], 4)
        
        # Support/Resistance (High/Low ក្នុងរយៈពេល ៥ ថ្ងៃ)
        res = round(df["High"].max(), 2)
        sup = round(df["Low"].min(), 2)
        eq_level = round((res + sup) / 2, 2)

        # គណនា RSI
        delta = df["Close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = round(100 - (100 / (1 + (gain / loss))).iloc[-1], 2)

        # គណនា MACD (Simple)
        exp1 = df["Close"].ewm(span=12, adjust=False).mean()
        exp2 = df["Close"].ewm(span=26, adjust=False).mean()
        macd = round((exp1 - exp2).iloc[-1], 2)
        signal_line = round((exp1 - exp2).ewm(span=9, adjust=False).mean().iloc[-1], 2)

        # ស្វែងរក FVG (Fair Value Gap) - ឧទាហរណ៍គំរូ
        # Bull FVG: Low(i) > High(i-2)
        bull_fvg = f"{round(df['Low'].iloc[-1], 2)} – {round(df['High'].iloc[-3], 2)}"
        
        return {
            "price": price, "high": high_h1, "low": low_h1, 
            "res": res, "sup": sup, "eq": eq_level, 
            "rsi": rsi, "macd": macd, "signal": signal_line,
            "fvg": bull_fvg
        }
    except Exception as e:
        logger.error(f"Analysis Error: {e}")
        return None

# --- Function ផ្ញើរបាយការណ៍ ---
async def send_full_report(context: ContextTypes.DEFAULT_TYPE, is_scheduled=False):
    data = await get_market_analysis()
    if not data: return

    # កំណត់ម៉ោងស្រុកខ្មែរ
    kh_tz = pytz.timezone('Asia/Phnom_Penh')
    now_kh = datetime.datetime.now(kh_tz)
    time_str = now_kh.strftime("%Y-%m-%d %H:%M")
    
    # --- លក្ខខណ្ឌ Monday - Friday (Market Open) ---
    day_of_week = now_kh.weekday() 
    if day_of_week < 5:
        status_market = "🟢 Market Open (Monday - Friday)"
    else:
        status_market = "⚠️ Weekend showing last available data (Weekend)"

    report = (
        "🏦 *E11 INTELLIGENCE — XAUUSD*\n"
        f"🕐 {time_str} (Cambodia)\n"
        f"{status_market}\n\n"
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
        f"  EQ Level    : ${data['eq']}\n"
        f"  Bull FVG    : {data['fvg']}\n\n"
        "📈 *INDICATORS*\n"
        f"  RSI (14)  : {data['rsi']} ✅\n"
        f"  MACD      : {data['macd']} | Signal: {data['signal']}\n\n"
        "🎯 *SIGNAL*\n"
        "  ⏳ WAIT\n"
        "  No clear signal — stay patient\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "E11 Sniper Bot • Educational use only"
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

# --- Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 E11 Sniper Bot Is Online!")

async def manual_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_full_report(context, is_scheduled=False)

# --- Main Logic ---
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    kh_tz = pytz.timezone('Asia/Phnom_Penh')
    scheduler = AsyncIOScheduler(timezone=kh_tz)

    # Schedule ផ្ញើរបាយការណ៍ ៣ ដងក្នុងមួយថ្ងៃ
    for hr in [8, 14, 19]:
        scheduler.add_job(
            send_full_report, 
            'cron', hour=hr, minute=0, 
            args=[app], name=f"Job_{hr}"
        )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("report", manual_report))

    async with app:
        await app.initialize()
        await app.start()
        scheduler.start()
        
        logger.info("✅ Bot running with Timezone: Asia/Phnom_Penh")
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
        logger.critical(f"Fatal Error: {e}")
    
