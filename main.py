import os, asyncio, pytz, datetime
from polygon import RESTClient
import pandas as pd
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
from threading import Thread

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
POLYGON_KEY = os.getenv("POLYGON_API_KEY")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
TOPIC_ID = os.getenv("TOPIC_ID")

client = RESTClient(POLYGON_KEY)

# --- WEB SERVER ---
app_web = Flask('')
@app_web.route('/')
def home(): return "E11 Intelligence Engine Active!"
def run(): app_web.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- LOGIC គណនាដោយដៃ (មិនប្រើ pandas_ta) ---
def calculate_ema(data, window):
    return data.ewm(span=window, adjust=False).mean()

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def get_smart_analysis():
    try:
        now = datetime.datetime.now(pytz.utc)
        start = (now - datetime.timedelta(days=15)).strftime('%Y-%m-%d')
        end = now.strftime('%Y-%m-%d')
        
        aggs = client.get_aggs("C:XAUUSD", 1, "hour", start, end)
        df = pd.DataFrame(aggs)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).dt.tz_convert('Asia/Phnom_Penh')
        
        # គណនា Indicator ដោយប្រើ Pandas សុទ្ធ
        df['ema200'] = calculate_ema(df['close'], 200)
        df['rsi'] = calculate_rsi(df['close'], 14)
        
        last_p = round(df['close'].iloc[-1], 2)
        ema200 = round(df['ema200'].iloc[-1], 2)
        rsi = round(df['rsi'].iloc[-1], 2)
        
        # BIAS Determination
        bias = "Bullish 📈" if last_p > ema200 else "Bearish 📉"
        action = "🚀 BUY (Discount Zone)" if rsi < 40 else "⚡️ SELL (Premium Zone)" if rsi > 60 else "🔍 Wait for Signal"

        now_kh = datetime.datetime.now(pytz.timezone('Asia/Phnom_Penh')).strftime('%Y-%m-%d %H:%M')

        return (
            f"🏦 *E11 INTELLIGENCE — XAUUSD*\n"
            f"🕐 {now_kh} (KH) | 🟢 Live Feed\n\n"
            f"📊 *MARKET SNAPSHOT*\n"
            f"💰 Price: `${last_p}`\n"
            f"⚡️ RSI (14): `{rsi}`\n"
            f"🌊 EMA 200: `${ema200}`\n\n"
            f"🧬 *FUNDAMENTAL & BIAS*\n"
            f"📉 Trend Bias: *{bias}*\n"
            f"🎯 *ACTION PLAN*\n"
            f"🏁 Action: *{action}*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"E11 Sniper Bot • AI Logic Engine"
        )
    except Exception as e:
        return f"❌ Error: {str(e)}"

# --- BOT HANDLERS ---
async def manual_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_smart_analysis(), parse_mode="Markdown")

async def auto_report(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=get_smart_analysis(), message_thread_id=TOPIC_ID, parse_mode="Markdown")

async def main():
    Thread(target=run).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("report", manual_report))
    
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Phnom_Penh'))
    for hr in [8, 14, 19, 21]:
        scheduler.add_job(auto_report, 'cron', hour=hr, minute=0, args=[app])
    scheduler.start()

    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
    
