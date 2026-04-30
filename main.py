import os, asyncio, pytz, datetime
from polygon import RESTClient
import pandas as pd
import pandas_ta as ta
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

def get_smart_analysis():
    try:
        # STEP 1: DATA GATHERING
        now = datetime.datetime.now(pytz.utc)
        start = (now - datetime.timedelta(days=10)).strftime('%Y-%m-%d')
        end = now.strftime('%Y-%m-%d')
        
        aggs = client.get_aggs("C:XAUUSD", 1, "hour", start, end)
        df = pd.DataFrame(aggs)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True).dt.tz_convert('Asia/Phnom_Penh')
        
        # STEP 2: BIAS DETERMINATION (Indicator Logic)
        df['ema200'] = ta.ema(df['close'], length=200)
        df['rsi'] = ta.rsi(df['close'], length=14)
        
        last_p = round(df['close'].iloc[-1], 2)
        ema200 = round(df['ema200'].iloc[-1], 2)
        rsi = round(df['rsi'].iloc[-1], 2)
        
        # Determine Bias
        if last_p > ema200:
            bias = "Bullish 📈"
            context = "តម្លៃនៅលើ EMA 200 (D1/H4) - ទីផ្សារមានកម្លាំងទិញខ្លាំង"
        else:
            bias = "Bearish 📉"
            context = "តម្លៃនៅក្រោម EMA 200 - ទីផ្សារស្ថិតក្នុងសម្ពាធលក់"

        # STEP 3: SCENARIO GENERATION
        if rsi > 70:
            scenario = "⚠️ OVERBOUGHT: រង់ចាំការទម្លាក់ថ្លៃ (Correction) មុននឹងរកឱកាសចូល"
            action = "⚡️ SELL (Scalp) ឬ Wait for Retest"
        elif rsi < 30:
            scenario = "⚠️ OVERSOLD: តម្លៃទាបខ្លាំង រកឱកាសងើបឡើងវិញ (Rebound)"
            action = "🚀 BUY (Discount Zone)"
        else:
            scenario = "⚖️ NEUTRAL: តម្លៃកំពុងរក្សាលំនឹងក្នុងតំបន់ Equilibrium"
            action = "🔍 រង់ចាំបំបែក PDH ឬ PDL"

        now_kh = datetime.datetime.now(pytz.timezone('Asia/Phnom_Penh')).strftime('%Y-%m-%d %H:%M')

        # CONTEXTUAL MESSAGE STRUCTURE
        msg = (
            f"🏦 *E11 INTELLIGENCE — XAUUSD*\n"
            f"🕐 {now_kh} (KH) | 🟢 Live Feed\n\n"
            f"📊 *MARKET SNAPSHOT*\n"
            f"💰 Price: `${last_p}`\n"
            f"⚡️ RSI (14): `{rsi}`\n"
            f"🌊 EMA 200: `${ema200}`\n\n"
            f"🧬 *FUNDAMENTAL & BIAS*\n"
            f"📉 Trend Bias: *{bias}*\n"
            f"📝 Context: {context}\n"
            f"⚠️ News: 🟡 Low Impact Day\n\n"
            f"🎯 *ACTION PLAN (SCENARIO)*\n"
            f"🎭 Scenario: {scenario}\n"
            f"🏁 Action: *{action}*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"E11 Sniper Bot • AI Logic Engine"
        )
        return msg
    except Exception as e:
        return f"❌ Error: {str(e)}"

# --- TELEGRAM BOT SETUP ---
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
    
