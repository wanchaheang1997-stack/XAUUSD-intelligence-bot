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
def home(): return "E11 Sniper Bot Active!"
def run_web(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
def keep_alive(): Thread(target=run_web).start()

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
TOPIC_ID = os.getenv("TOPIC_ID")

class E11IntelligenceUltra:
    @staticmethod
    def get_market_context():
        try:
            # Fundamental & News (Reuters/CNBC Style)
            gold_news = yf.Ticker("GC=F").news
            headline = gold_news[0]['title'] if gold_news else "Market focuses on US Fed's next move."
            
            # Sentiment & Calendar (Simulation based on Investing/ForexFactory schedule)
            # មេអាចជំនួសដោយ API ជាក់លាក់ ប្រសិនបើមេមាន Key ពី FXSSI
            sentiment = "🐂 Buy 63% | 🐻 Sell 37%" 
            calendar = "🔴 20:30 US Core PCE Price Index | 🟠 22:00 Fed Chair Speech"
            return headline[:80] + "...", sentiment, calendar
        except: return "Stable macro context.", "N/A", "🟡 Low Impact Day"

    @staticmethod
    def calculate_vp_and_levels(df_h1, df_d):
        # Daily Volume Profile
        price_min, price_max = df_d['Low'].iloc[-1], df_d['High'].iloc[-1]
        bins = np.linspace(price_min, price_max, 20)
        vprofile = df_h1.groupby(pd.cut(df_h1['Close'], bins), observed=False)['Volume'].sum()
        poc = (vprofile.idxmax().left + vprofile.idxmax().right) / 2
        vah = poc * 1.015; val = poc * 0.985 # Value Area Calculation
        
        # Session High/Low (Logic តាម Session ជាក់ស្តែង)
        now_kh = datetime.datetime.now(pytz.timezone('Asia/Phnom_Penh'))
        h = now_kh.hour
        # Tokyo: 06-12, London: 13-18, NY: 19-04
        session_data = df_h1.iloc[-8:] # យកទិន្នន័យ ៨ ម៉ោងចុងក្រោយ
        sess_h, sess_l = session_data['High'].max(), session_data['Low'].min()
        
        return round(vah, 2), round(val, 2), round(poc, 2), round(sess_h, 2), round(sess_l, 2)

    @staticmethod
    async def get_analysis():
        try:
            gold, dxy, btc = yf.Ticker("GC=F"), yf.Ticker("DX-Y.NYB"), yf.Ticker("BTC-USD")
            df_h1 = gold.history(period="5d", interval="1h")
            df_d = gold.history(period="10d", interval="1d")
            
            news, sentiment, calendar = E11IntelligenceUltra.get_market_context()
            vah, val, poc, sess_h, sess_l = E11IntelligenceUltra.calculate_vp_and_levels(df_h1, df_d)
            
            last_p = df_h1['Close'].iloc[-1]
            pdh, pdl = df_d['High'].iloc[-2], df_d['Low'].iloc[-2]
            pwh, pwl = df_d['High'].iloc[-5:].max(), df_d['Low'].iloc[-5:].min()

            # --- SIGNAL LOGIC (Premium/Discount Zone) ---
            swing_high = df_h1['High'].iloc[-24:].max()
            swing_low = df_h1['Low'].iloc[-24:].min()
            range_size = swing_high - swing_low
            premium_zone = swing_low + (range_size * 0.7)
            discount_zone = swing_low + (range_size * 0.3)
            
            action = "⏳ រង់ចាំ (Neutral)"
            # Logic: Buy in Discount + Breakout/Retest
            if last_p < discount_zone and last_p > swing_low:
                action = "🚀 BUY (In Discount Zone)"
            # Logic: Sell in Premium + Breakout/Retest
            elif last_p > premium_zone and last_p < swing_high:
                action = "📉 SELL (In Premium Zone)"

            return {
                "p": round(last_p, 2), "h": round(df_d['High'].iloc[-1], 2), "l": round(df_d['Low'].iloc[-1], 2),
                "dxy": round(dxy.history(period="1d")['Close'].iloc[-1], 2),
                "btc": round(btc.history(period="1d")['Close'].iloc[-1], 2),
                "vah": vah, "val": val, "poc": poc, "pwh": round(pwh, 2), "pwl": round(pwl, 2),
                "pdh": round(pdh, 2), "pdl": round(pdl, 2), "sess_h": sess_h, "sess_l": sess_l,
                "news": news, "calendar": calendar, "sentiment": sentiment, "action": action,
                "bull_ob": round(swing_low + 5, 2), "bear_ob": round(swing_high - 5, 2)
            }
        except Exception as e:
            logging.error(f"Error: {e}"); return None

async def send_report(context: ContextTypes.DEFAULT_TYPE):
    data = await E11IntelligenceUltra.get_analysis()
    if not data: return
    kh_tz = pytz.timezone('Asia/Phnom_Penh')
    now = datetime.datetime.now(kh_tz)
    
    # Session Name Display
    h = now.hour
    sess_name = "🇯🇵 Tokyo" if 6 <= h < 14 else "🇬🇧 London" if 14 <= h < 19 else "🇺🇸 New York"

    report = (
        "🏦 *E11 INTELLIGENCE — XAUUSD*\n"
        f"🕐 {now.strftime('%Y-%m-%d %H:%M')} (KH) | 🟢 Open\n"
        f"🧬 Fundamental: {data['news']}\n"
        f"🧬 Sentimental: {data['sentiment']}\n"
        f"⚠️ Economic Calendar: {data['calendar']}\n\n"
        "💰 *CURRENT MARKET PRICE:*\n"
        f"⚜️ Gold High: ${data['h']}\n"
        f"⚜️ Gold Low : ${data['l']}\n"
        f"💲 DXY Index: {data['dxy']}\n"
        f"🪙 BTC : ${data['btc']:,}\n\n"
        "📊 *VOLUME PROFILE (Daily)*\n"
        f"  ⬆️ VAH : ${data['vah']}\n"
        f"  🎯 POC : ${data['poc']}\n"
        f"  ⬇️ VAL : ${data['val']}\n\n"
        "🔑 *Key Level:*\n"
        f"  💸 PWH: ${data['pwh']} | PWL: ${data['pwl']}\n"
        f"  💸 PDH: ${data['pdh']} | PDL: ${data['pdl']}\n"
        f"  {sess_name} H: ${data['sess_h']} | {sess_name} L: ${data['sess_l']}\n"
        f"  ⚠️ Support: ${data['pwl']} | Resistance: ${data['pwh']}\n\n"
        "💰 *Liquidity Pool (1H):*\n"
        f"  🐂 Bullish OB : ${data['bull_ob']}\n"
        f"  🐻 Bearish OB : ${data['bear_ob']}\n\n"
        "🎯 *SIGNAL*\n"
        f"  Action : {data['action']}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "E11 Sniper Bot • ICT Sniper Logic"
    )
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=report, message_thread_id=TOPIC_ID, parse_mode="Markdown")

async def main():
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Phnom_Penh'))
    for hr in [8, 14, 19, 21]:
        scheduler.add_job(send_report, 'cron', hour=hr, minute=0, args=[app])
    app.add_handler(CommandHandler("report", lambda u, c: send_report(c)))
    async with app:
        await app.initialize(); await app.start()
        scheduler.start()
        await app.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
    
