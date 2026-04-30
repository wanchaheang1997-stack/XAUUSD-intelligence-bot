import os, asyncio, pytz, datetime
from polygon import RESTClient
import pandas as pd
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
from threading import Thread

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
POLYGON_KEY = os.getenv("POLYGON_API_KEY")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
REPORT_TOPIC_ID = os.getenv("TOPIC_ID")        # Topic សម្រាប់របាយការណ៍
SIGNAL_TOPIC_ID = os.getenv("SIGNAL_TOPIC_ID") # Topic សម្រាប់ Signal (LuxAlgo)

client = RESTClient(POLYGON_KEY)

# --- WEB SERVER (For Render Health Check) ---
app_web = Flask('')
@app_web.route('/')
def home(): return "E11 Intelligence Engine is Running!"
def run(): app_web.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- ENGINE 1: DAILY REPORT LOGIC ---
def get_report_analysis():
    try:
        now = datetime.datetime.now(pytz.utc)
        aggs = client.get_aggs("C:XAUUSD", 1, "hour", (now - datetime.timedelta(days=10)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'))
        df = pd.DataFrame(aggs)
        last_p = round(df['close'].iloc[-1], 2)
        
        # គណនា EMA 200 សម្រាប់ Bias
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        bias = "Bullish 📈" if last_p > df['ema200'].iloc[-1] else "Bearish 📉"
        
        now_kh = datetime.datetime.now(pytz.timezone('Asia/Phnom_Penh')).strftime('%Y-%m-%d %H:%M')
        return (
            f"🏦 *E11 DAILY INTELLIGENCE*\n"
            f"🕐 {now_kh} (KH)\n"
            f"💰 Price: `${last_p}`\n"
            f"📉 Trend Bias: *{bias}*\n"
            f"📝 ទីផ្សារកំពុងស្ថិតក្នុងតំបន់តាមដាន..."
        )
    except: return "❌ Report Data Error"

# --- ENGINE 2: LUXALGO SIGNAL LOGIC (M15) ---
def check_luxalgo_signal():
    try:
        now = datetime.datetime.now(pytz.utc)
        aggs = client.get_aggs("C:XAUUSD", 15, "minute", (now - datetime.timedelta(days=5)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'))
        df = pd.DataFrame(aggs)
        length = 14
        
        # ATR Slope
        df['tr'] = np.maximum(df['high'] - df['low'], np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))))
        slope = (df['tr'].rolling(window=length).mean() / length)
        
        # Pivot High/Low
        df['ph'] = np.where((df['high'] == df['high'].rolling(window=length*2+1, center=True).max()), df['high'], np.nan)
        df['pl'] = np.where((df['low'] == df['low'].rolling(window=length*2+1, center=True).min()), df['low'], np.nan)
        
        upper, lower = np.zeros(len(df)), np.zeros(len(df))
        u_slp, l_slp = 0, 0
        upper[0], lower[0] = df['high'].iloc[0], df['low'].iloc[0]
        
        for i in range(1, len(df)):
            if not np.isnan(df['ph'].iloc[i]): 
                upper[i], u_slp = df['ph'].iloc[i], slope.iloc[i]
            else: 
                upper[i] = upper[i-1] - u_slp
            if not np.isnan(df['pl'].iloc[i]): 
                lower[i], l_slp = df['pl'].iloc[i], slope.iloc[i]
            else: 
                lower[i] = lower[i-1] + l_slp

        last_c, prev_c = df['close'].iloc[-1], df['close'].iloc[-2]
        if last_c > upper[-1] and prev_c <= upper[-2]: return "🚀 UPWARD BREAK (BUY)", last_c
        if last_c < lower[-1] and prev_c >= lower[-2]: return "⚡️ DOWNWARD BREAK (SELL)", last_c
        return None, last_c
    except: return None, None

# --- AUTOMATED TASKS ---
async def job_scheduled_report(context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=get_report_analysis(), message_thread_id=REPORT_TOPIC_ID, parse_mode="Markdown")

async def job_scan_signals(context: ContextTypes.DEFAULT_TYPE):
    signal, price = check_luxalgo_signal()
    if signal:
        msg = (
            f"🚨 *LUXALGO M15 SIGNAL*\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Signal: *{signal}*\n"
            f"💰 Entry: `${price}`\n"
            f"⏰ Time: {datetime.datetime.now(pytz.timezone('Asia/Phnom_Penh')).strftime('%H:%M')} (KH)\n"
            f"━━━━━━━━━━━━━━━━━━━"
        )
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=msg, message_thread_id=SIGNAL_TOPIC_ID, parse_mode="Markdown")

# --- MAIN ---
async def main():
    Thread(target=run).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Phnom_Penh'))

    # Task 1: បាញ់ Report តាមម៉ោង (Topic 1)
    for hr in [8, 14, 19, 21]:
        scheduler.add_job(job_scheduled_report, 'cron', hour=hr, minute=0, args=[app])

    # Task 2: យាម Signal រៀងរាល់ ១ នាទី (Topic 2)
    scheduler.add_job(job_scan_signals, 'interval', minutes=1, args=[app])
    
    scheduler.start()
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
            
