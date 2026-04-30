import os, asyncio, pytz, datetime, logging
from polygon import RESTClient
import pandas as pd
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
from threading import Thread

# Logging Setup
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
def home(): return "E11 Sniper Bot is Online!"
def run(): app_web.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- ENGINE 1: FULL REPORT LOGIC ---
async def get_report_text():
    try:
        now = datetime.datetime.now(pytz.utc)
        start_date = (now - datetime.timedelta(days=10)).strftime('%Y-%m-%d')
        aggs = client.get_aggs("C:XAUUSD", 1, "hour", start_date, now.strftime('%Y-%m-%d'))
        df = pd.DataFrame(aggs)
        if df.empty: return "❌ No Data Found"
        
        last_p = round(df['close'].iloc[-1], 2)
        
        # 1. RSI (14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rsi = round(100 - (100 / (1 + (gain/loss))).iloc[-1], 2)
        
        # 2. EMA 200 & Bias
        ema200 = round(df['close'].ewm(span=200, adjust=False).mean().iloc[-1], 2)
        bias = "Bullish 📈" if last_p > ema200 else "Bearish 📉"
        
        # 3. Pivot Points (S/R)
        h, l, c = df['high'].iloc[-2], df['low'].iloc[-2], df['close'].iloc[-2]
        pivot = (h + l + c) / 3
        r1 = round(2 * pivot - l, 2)
        s1 = round(2 * pivot - h, 2)
        
        now_kh = datetime.datetime.now(pytz.timezone('Asia/Phnom_Penh')).strftime('%H:%M')
        return (
            f"🏦 *E11 MARKET INTELLIGENCE*\n"
            f"💰 Price: `${last_p}`\n"
            f"⚡ RSI (14): `{rsi}`\n"
            f"🌊 EMA 200: `${ema200}`\n\n"
            f"📉 *BIAS:* {bias}\n"
            f"🚧 *Resistance:* `${r1}`\n"
            f"🛡 *Support:* `${s1}`\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ Time: {now_kh} (KH) • E11 Sniper"
        )
    except Exception as e:
        return f"❌ Analysis Error: {e}"

# --- ENGINE 2: LUXALGO SIGNAL LOGIC (M15) ---
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
        if last_c > upper[-1] and prev_c <= upper[-2]: return "🚀 BUY (Breakout Up)", last_c
        if last_c < lower[-1] and prev_c >= lower[-2]: return "⚡️ SELL (Breakout Down)", last_c
        return None, last_c
    except: return None, None

# --- AUTOMATION JOBS ---
async def job_report(context: ContextTypes.DEFAULT_TYPE):
    text = await get_report_text()
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=text, message_thread_id=REPORT_TOPIC_ID, parse_mode="Markdown")

async def job_signal(context: ContextTypes.DEFAULT_TYPE):
    sig, price = await check_luxalgo_signal()
    if sig:
        msg = f"🚨 *LUXALGO M15 SIGNAL*\n🎯 Action: *{sig}*\n💰 Price: `${price}`\nE11 Sniper Bot"
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=msg, message_thread_id=SIGNAL_TOPIC_ID, parse_mode="Markdown")

# --- COMMANDS ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("E11 Sniper Bot is Online! 🎯")

async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = await get_report_text()
    await update.message.reply_text(text, parse_mode="Markdown")

# --- MAIN RUNNER ---
async def main():
    Thread(target=run).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Phnom_Penh'))
    for hr in [8, 14, 19, 21]:
        scheduler.add_job(job_report, 'cron', hour=hr, minute=0, args=[app])
    scheduler.add_job(job_signal, 'interval', minutes=2, args=[app])
    
    scheduler.start()
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception: pass
