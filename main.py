import os, logging, datetime, asyncio, pytz, requests
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask
from threading import Thread
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- WEB SERVER FOR RENDER ---
app = Flask('')
@app.route('/')
def home(): return "E11 Sniper Bot Active!"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
def keep_alive(): Thread(target=run_web).start()

# --- CONFIG ---
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
TOPIC_ID = os.getenv("TOPIC_ID")
ALERT_TOPIC = os.getenv("ALERT_TOPIC") # លេខ 3 ដែលមេដាក់ក្នុង Render

class E11IntelligenceUltra:
    @staticmethod
    def get_analysis_data():
        try:
            gold = yf.Ticker("GC=F")
            df_h1 = gold.history(period="5d", interval="1h")
            df_d = gold.history(period="10d", interval="1d")
            
            # Volume Profile & Levels
            last_p = df_h1['Close'].iloc[-1]
            pwh, pwl = df_d['High'].iloc[-5:].max(), df_d['Low'].iloc[-5:].min()
            
            # Premium/Discount Logic
            swing_h, swing_l = df_h1['High'].iloc[-24:].max(), df_h1['Low'].iloc[-24:].min()
            range_s = swing_h - swing_l
            premium, discount = swing_l + (range_s * 0.7), swing_l + (range_s * 0.3)
            
            return {
                "p": round(last_p, 2), "pwh": round(pwh, 2), "pwl": round(pwl, 2),
                "premium": premium, "discount": discount, "df_h1": df_h1, "df_d": df_d
            }
        except Exception as e:
            logger.error(f"Data Fetch Error: {e}"); return None

# --- FUNCTION សម្រាប់ ALERT ភ្លាមៗ (បាញ់ចូល Topic 3) ---
async def price_monitor(context: ContextTypes.DEFAULT_TYPE):
    data = await E11IntelligenceUltra.get_analysis_data()
    if not data: return
    
    last_p = data['p']
    target_topic = ALERT_TOPIC if ALERT_TOPIC else TOPIC_ID

    # Alert ពេលបុក Resistance ឬចូលតំបន់លក់
    if last_p >= data['pwh']:
        msg = f"🔴 *SNIPER ALERT: SELL ZONE*\n\n⚜️ Price: ${last_p}\n🎯 Level: Resistance (PWH)\n⚡️ Status: Extreme Premium\n\n*E11 Sniper Logic*"
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=msg, message_thread_id=target_topic, parse_mode="Markdown")
    
    # Alert ពេលបុក Support ឬចូលតំបន់ទិញ
    elif last_p <= data['pwl']:
        msg = f"🟢 *SNIPER ALERT: BUY ZONE*\n\n⚜️ Price: ${last_p}\n🎯 Level: Support (PWL)\n⚡️ Status: Extreme Discount\n\n*E11 Sniper Logic*"
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=msg, message_thread_id=target_topic, parse_mode="Markdown")

# --- FUNCTION សម្រាប់ REPORT តាមម៉ោង (បាញ់ចូល Topic ដើម) ---
async def send_report(context: ContextTypes.DEFAULT_TYPE):
    # (មេអាចប្រើកូដ Report ចាស់ដែលបងធ្លាប់ឱ្យពីមុនបាន ឬប្រើទម្រង់សង្ខេបនេះ)
    data = await E11IntelligenceUltra.get_analysis_data()
    if not data: return
    report = f"🏦 *E11 DAILY REPORT*\n💰 Price: ${data['p']}\n📊 Range: ${data['pwl']} - ${data['pwh']}\n━━━━━━━━━━━━━━━━━━━"
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=report, message_thread_id=TOPIC_ID, parse_mode="Markdown")

async def main():
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Phnom_Penh'))
    
    # កំណត់ម៉ោង Report (Topic 1)
    for hr in [8, 14, 19, 21]:
        scheduler.add_job(send_report, 'cron', hour=hr, minute=0, args=[app])

    # កំណត់ឱ្យ Monitor តម្លៃរៀងរាល់ ១ នាទី (Topic 3)
    scheduler.add_job(price_monitor, 'interval', minutes=1, args=[app])

    async with app:
        await app.initialize(); await app.start()
        scheduler.start()
        logger.info("E11 Sniper Bot is Online!")
        await app.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
    
