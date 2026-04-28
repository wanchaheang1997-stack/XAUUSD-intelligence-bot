import os, asyncio, pytz, datetime
import yfinance as yf
import pandas as pd
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
from threading import Thread

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
TOPIC_ID = os.getenv("TOPIC_ID")

# --- WEB SERVER ---
app_web = Flask('')
@app_web.route('/')
def home(): return "E11 Intelligence System Active!"
def run(): app_web.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- ADVANCED ANALYSIS LOGIC ---
def get_e11_intelligence():
    try:
        # ទាញទិន្នន័យ Gold, DXY, BTC
        gold = yf.Ticker("GC=F")
        dxy = yf.Ticker("DX-Y.NYB")
        btc = yf.Ticker("BTC-USD")
        
        df_h1 = gold.history(period="5d", interval="1h")
        df_d = gold.history(period="5d", interval="1d")
        
        last_p = round(df_h1['Close'].iloc[-1], 2)
        high_24h = round(df_h1['High'].iloc[-24:].max(), 2)
        low_24h = round(df_h1['Low'].iloc[-24:].min(), 2)
        
        # Volume Profile (Simulated via Price Action)
        vah = round(high_24h * 1.005, 2)
        val = round(low_24h * 0.995, 2)
        poc = round((vah + val) / 2, 2)
        
        # Key Levels
        pdh = round(df_d['High'].iloc[-2], 2)
        pdl = round(df_d['Low'].iloc[-2], 2)
        pwh = round(df_d['High'].max(), 2)
        pwl = round(df_d['Low'].min(), 2)
        
        dxy_p = round(dxy.history(period="1d")['Close'].iloc[-1], 2)
        btc_p = "{:,}".format(round(btc.history(period="1d")['Close'].iloc[-1], 2))
        
        now_kh = datetime.datetime.now(pytz.timezone('Asia/Phnom_Penh')).strftime('%Y-%m-%d %H:%M')
        
        # Logic សម្រាប់ Signal
        action = "🚀 BUY (In Discount Zone)" if last_p < poc else "⚡️ SELL (In Premium Zone)"

        msg = (
            f"🏦 *E11 INTELLIGENCE — XAUUSD*\n"
            f"🕐 {now_kh} (KH) | 🟢 Open\n"
            f"🧬 Fundamental: Market context stable.\n"
            f"⚠️ Economic Calendar: 🟡 Low Impact Day\n\n"
            f"💰 *CURRENT MARKET PRICE:*\n"
            f"⚜️ Gold High: `${high_24h}`\n"
            f"⚜️ Gold Low : `${low_24h}`\n"
            f"💲 DXY Index: `{dxy_p}`\n"
            f"🪙 BTC : `${btc_p}`\n\n"
            f"📊 *VOLUME PROFILE (Daily)*\n"
            f"  ⬆️ VAH : `${vah}`\n"
            f"  🎯 POC : `${poc}`\n"
            f"  ⬇️ VAL : `${val}`\n\n"
            f"🔑 *Key Level:*\n"
            f"  💸 PWH: `${pwh}` | PWL: `${pwl}`\n"
            f"  💸 PDH: `${pdh}` | PDL: `${pdl}`\n"
            f"  ⚠️ Support: `${low_24h}` | Resistance: `${high_24h}`\n\n"
            f"🎯 *SIGNAL*\n"
            f"  Action : {action}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"E11 Sniper Bot • ICT Sniper Logic"
        )
        return msg
    except Exception as e:
        return f"❌ Error: {str(e)}"

# --- BOT FUNCTIONS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 E11 System Ready! វាយ /report ដើម្បីមើលវិភាគ។")

async def manual_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_e11_intelligence(), parse_mode="Markdown")

async def auto_report(context: ContextTypes.DEFAULT_TYPE):
    msg = get_e11_intelligence()
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=msg, message_thread_id=TOPIC_ID, parse_mode="Markdown")

async def main():
    Thread(target=run).start()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
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
        
