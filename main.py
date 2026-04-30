import os, asyncio, pytz, datetime, logging
from polygon import RESTClient
import pandas as pd
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
from threading import Thread

# បើកមើល Error ក្នុង Render Logs ឱ្យច្បាស់បំផុត
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
POLYGON_KEY = os.getenv("POLYGON_API_KEY")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
REPORT_TOPIC_ID = os.getenv("TOPIC_ID")        
SIGNAL_TOPIC_ID = os.getenv("SIGNAL_TOPIC_ID") 

client = RESTClient(POLYGON_KEY)

# --- WEB SERVER ---
app_web = Flask('')
@app_web.route('/')
def home(): return "E11 Intelligence Engine is Online!"
def run(): app_web.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- ENGINE 1: REPORT ---
async def get_report_text():
    try:
        now = datetime.datetime.now(pytz.utc)
        start_date = (now - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        # ទាញទិន្នន័យ
        aggs = client.get_aggs("C:XAUUSD", 1, "hour", start_date, now.strftime('%Y-%m-%d'))
        df = pd.DataFrame(aggs)
        if df.empty: return "❌ មិនអាចទាញទិន្នន័យបានទេ"
        
        last_p = round(df['close'].iloc[-1], 2)
        now_kh = datetime.datetime.now(pytz.timezone('Asia/Phnom_Penh')).strftime('%H:%M')
        return f"🏦 *E11 REPORT*\n💰 Price: `${last_p}`\n⏰ Time: {now_kh}\nStatus: Bot Is Running ✅"
    except Exception as e:
        logging.error(f"Report Error: {e}")
        return "❌ Error ក្នុងការគណនា Report"

# --- ENGINE 2: LUXALGO SIGNAL ---
async def check_luxalgo_signal():
    try:
        now = datetime.datetime.now(pytz.utc)
        start_date = (now - datetime.timedelta(days=3)).strftime('%Y-%m-%d')
        aggs = client.get_aggs("C:XAUUSD", 15, "minute", start_date, now.strftime('%Y-%m-%d'))
        df = pd.DataFrame(aggs)
        if df.empty: return None, None

        length = 14
        df['tr'] = np.maximum(df['high'] - df['low'], np.maximum(abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))))
        slope = (df['tr'].rolling(window=length).mean() / length)
        df['ph'] = np.where((df['high'] == df['high'].rolling(window=length*2+1, center=True).max()), df['high'], np.nan)
        df['pl'] = np.where((df['low'] == df['low'].rolling(window=length*2+1, center=True).min()), df['low'], np.nan)
        
        upper, lower = np.zeros(len(df)), np.zeros(len(df))
        u_slp, l_slp = 0, 0
        upper[0], lower[0] = df['high'].iloc[0], df['low'].iloc[0]
        for i in range(1, len(df)):
            if not np.isnan(df['ph'].iloc[i]): upper[i], u_slp = df['ph'].iloc[i], slope.iloc[i]
            else: upper[i] = upper[i-1] - u_slp
            if not np.isnan(df['pl'].iloc[i]): lower[i], l_slp = df['pl'].iloc[i], slope.iloc[i]
            else: lower[i] = lower[i-1] + l_slp
        
        last_c, prev_c = df['close'].iloc[-1], df['close'].iloc[-2]
        if last_c > upper[-1] and prev_c <= upper[-2]: return "🚀 BUY (Break Up)", last_c
        if last_c < lower[-1] and prev_c >= lower[-2]: return "⚡️ SELL (Break Down)", last_c
        return None, last_c
    except Exception as e:
        logging.error(f"Signal Error: {e}")
        return None, None

# --- TASKS ---
async def job_report(context: ContextTypes.DEFAULT_TYPE):
    text = await get_report_text()
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=text, message_thread_id=REPORT_TOPIC_ID, parse_mode="Markdown")

async def job_signal(context: ContextTypes.DEFAULT_TYPE):
    sig, price = await check_luxalgo_signal()
    if sig:
        msg = f"🚨 *LUXALGO SIGNAL*\n🎯 Action: *{sig}*\n💰 Price: `${price}`\nE11 Sniper"
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=msg, message_thread_id=SIGNAL_TOPIC_ID, parse_mode="Markdown")

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("E11 Sniper Bot is Online! 🎯")

async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await get_report_text()
    await update.message.reply_text(text, parse_mode="Markdown")

# --- MAIN ---
async def main():
    Thread(target=run).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # ដាក់ Command ឱ្យ Bot ស្គាល់
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Phnom_Penh'))
    # បាញ់ Report តាមម៉ោង
    for hr in [8, 14, 19, 21]:
        scheduler.add_job(job_report, 'cron', hour=hr, minute=0, args=[app])
    # យាម Signal រៀងរាល់ ២ នាទី (កុំឱ្យញឹកពេកនាំឱ្យស្ទះ API)
    scheduler.add_job(job_signal, 'interval', minutes=2, args=[app])
    
    scheduler.start()
    logging.info("Bot and Scheduler Started...")
    
    async with app:
        await app.initialize()
        await app.start()
        # សំខាន់៖ ប្រើ polling បែបសាមញ្ញបំផុតដើម្បីជៀសវាង Conflict
        await app.updater.start_polling()
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.fatal(f"Fatal Error: {e}")
        
