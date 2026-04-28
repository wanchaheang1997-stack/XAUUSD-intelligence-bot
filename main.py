import os, logging, datetime, asyncio, pytz, requests
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask
from threading import Thread
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- WEB SERVER FOR RENDER (KEEP ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "E11 Sniper Bot is Running!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# --- CONFIG & LOGGING ---
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
TOPIC_ID = os.getenv("TOPIC_ID")
ALERT_TOPIC = os.getenv("ALERT_TOPIC") # បន្ថែម Topic ទី២ សម្រាប់ Alert

class E11IntelligenceUltra:
    @staticmethod
    def get_sentiment():
        try:
            buy_pct, sell_pct = 63, 37 
            return f"🐂 Buy {buy_pct}% | 🐻 Sell {sell_pct}%"
        except: return "N/A"

    @staticmethod
    def get_market_insights():
        try:
            news_list = yf.Ticker("GC=F").news
            headline = news_list[0]['title'] if news_list else "Market consolidating..."
            calendar = "🔴 High: US Core PCE (20:30) | 🟠 Med: Jobless Claims"
            return headline[:65] + "...", calendar
        except: return "Stable macro context.", "🟡 Low Impact Day"

    @staticmethod
    def calculate_volume_profile(df):
        price_min, price_max = df['Low'].min(), df['High'].max()
        bins = np.linspace(price_min, price_max, 25)
        vprofile = df.groupby(pd.cut(df['Close'], bins), observed=False)['Volume'].sum()
        poc = (vprofile.idxmax().left + vprofile.idxmax().right) / 2
        v_sorted = vprofile.sort_values(ascending=False)
        v_area = v_sorted[v_sorted.cumsum() <= vprofile.sum() * 0.7].index
        vah = max([b.right for b in v_area]) if not v_area.empty else poc * 1.01
        val = min([b.left for b in v_area]) if not v_area.empty else poc * 0.99
        return round(vah, 2), round(val, 2), round(poc, 2)

    @staticmethod
    def calculate_rsi(series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        return round(100 - (100 / (1 + (gain / loss))).iloc[-1], 2)

    @staticmethod
    async def get_full_analysis():
        try:
            gold, dxy, btc = yf.Ticker("GC=F"), yf.Ticker("DX-Y.NYB"), yf.Ticker("BTC-USD")
            df_h1 = gold.history(period="7d", interval="1h")
            df_d = gold.history(period="10d", interval="1d")
            news, calendar = E11IntelligenceUltra.get_market_insights()
            sentiment = E11IntelligenceUltra.get_sentiment()
            vah, val, poc = E11IntelligenceUltra.calculate_volume_profile(df_h1)
            rsi = E11IntelligenceUltra.calculate_rsi(df_h1['Close'])
            pdh, pdl = df_d['High'].iloc[-2], df_d['Low'].iloc[-2]
            pwh, pwl = df_d['High'].iloc[-5:].max(), df_d['Low'].iloc[-5:].min()
            asia = df_h1.between_time('23:00', '08:00')
            asia_h, asia_l = asia['High'].max(), asia['Low'].min()
            last_p = df_h1['Close'].iloc[-1]
            
            action = "⏳ រង់ចាំ (Neutral)"
            if rsi <= 30 or (abs(last_p - poc) <= 1 and rsi < 45): action = "🚀 ឱកាសទិញ (Oversold/FV Retest)"
            elif rsi >= 80 or (abs(last_p - poc) <= 1 and rsi > 55): action = "📉 ឱកាសលក់ (Overbought/FV Retest)"

            return {
                "p": round(last_p, 2), "h": round(df_h1['High'].iloc[-24:].max(), 2),
                "l": round(df_h1['Low'].iloc[-24:].min(), 2), "dxy": round(dxy.history(period="1d")['Close'].iloc[-1], 2),
                "btc": round(btc.history(period="1d")['Close'].iloc[-1], 2),
                "vah": vah, "val": val, "poc": poc, "pwh": round(pwh, 2), "pwl": round(pwl, 2),
                "pdh": round(pdh, 2), "pdl": round(pdl, 2), "asia_h": round(asia_h, 2),
                "asia_l": round(asia_l, 2), "news": news, "calendar": calendar,
                "sentiment": sentiment, "rsi": rsi, "action": action,
                "bull_ob": round(df_h1[df_h1['Close'] < df_h1['Open']]['Low'].iloc[-1], 2),
                "bear_ob": round(df_h1[df_h1['Close'] > df_h1['Open']]['High'].iloc[-1], 2)
            }
        except Exception as e:
            logger.error(f"Logic Error: {e}"); return None

async def send_report(context: ContextTypes.DEFAULT_TYPE):
    data = await E11IntelligenceUltra.get_full_analysis()
    if not data: return
    kh_tz = pytz.timezone('Asia/Phnom_Penh')
    now = datetime.datetime.now(kh_tz)
    
    report = (
        "🏦 *E11 INTELLIGENCE — XAUUSD*\n"
        f"🕐 {now.strftime('%Y-%m-%d %H:%M')} (KH) | 🟢 Open\n"
        f"🧬 *Fundamental:* {data['news']}\n"
        f"🧬 *Sentimental:* {data['sentiment']}\n"
        f"⚠️ *Calendar:* {data['calendar']}\n\n"
        "💰 *CURRENT MARKET PRICE:*\n"
        f"⚜️ Gold High: ${data['h']}\n"
        f"⚜️ Gold Low : ${data['l']}\n"
        f"💲 DXY Index: {data['dxy']}\n"
        f"🪙 BTC : ${data['btc']:,}\n\n"
        "📊 *VOLUME PROFILE*\n"
        f"  ⬆️ VAH : ${data['vah']}\n"
        f"  🎯 POC : ${data['poc']}\n"
        f"  ⬇️ VAL : ${data['val']}\n\n"
        "🔑 *Key Level:*\n"
        f"  💸 PWH: ${data['pwh']} | PWL: ${data['pwl']}\n"
        f"  💸 PDH: ${data['pdh']} | PDL: ${data['pdl']}\n"
        f"  🇯🇵 Asia H: ${data['asia_h']} | Asia L: ${data['asia_l']}\n"
        f"  ⚠️ Support: ${data['pwl']} | Resistance: ${data['pwh']}\n\n"
        "💰 *Liquidity Pool (1H):*\n"
        f"  🐂 Bullish OB : ${data['bull_ob']}\n"
        f"  🐻 Bearish OB : ${data['bear_ob']}\n\n"
        "🎯 *SIGNAL*\n"
        f"  Action : {data['action']}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "E11 Sniper Bot • ICT Sniper Logic"
    )
    # ផ្ញើទៅ Topic ដើម
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=report, message_thread_id=TOPIC_ID, parse_mode="Markdown")

async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is missing!"); return

    # Start Web Server
    keep_alive()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Phnom_Penh'))
    
    # Schedule Report 8AM, 2PM, 7PM, 9PM KH
    for hr in [8, 14, 19, 21]:
        scheduler.add_job(send_report, 'cron', hour=hr, minute=0, args=[app])

    app.add_handler(CommandHandler("report", lambda u, c: send_report(c)))
    
    async with app:
        await app.initialize()
        await app.start()
        scheduler.start()
        logger.info("Bot is active and scheduler started.")
        await app.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
            
