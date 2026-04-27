import os, logging, datetime, asyncio, pytz
import yfinance as yf
import pandas as pd
import numpy as np
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- CONFIG ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
TOPIC_ID = os.getenv("TOPIC_ID")

class E11IntelligenceEngine:
    @staticmethod
    def calculate_volume_profile(df):
        price_min, price_max = df['Low'].min(), df['High'].max()
        bins = np.linspace(price_min, price_max, 20)
        vprofile = df.groupby(pd.cut(df['Close'], bins), observed=False)['Volume'].sum()
        poc_bin = vprofile.idxmax()
        poc = (poc_bin.left + poc_bin.right) / 2
        total_vol = vprofile.sum()
        v_sorted = vprofile.sort_values(ascending=False)
        cumulative_vol = v_sorted.cumsum()
        v_area_bins = v_sorted[cumulative_vol <= total_vol * 0.7].index
        vah = max([b.right for b in v_area_bins]) if not v_area_bins.empty else poc * 1.01
        val = min([b.left for b in v_area_bins]) if not v_area_bins.empty else poc * 0.99
        return round(vah, 2), round(val, 2), round(poc, 2)

    @staticmethod
    def calculate_rsi(series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return round(100 - (100 / (1 + rs)).iloc[-1], 2)

    @staticmethod
    async def get_market_data():
        try:
            gold = yf.Ticker("GC=F")
            dxy = yf.Ticker("DX-Y.NYB")
            btc = yf.Ticker("BTC-USD")
            
            df_h1 = gold.history(period="7d", interval="1h")
            df_d = gold.history(period="5d", interval="1d")
            dxy_p = dxy.history(period="1d")['Close'].iloc[-1]
            btc_p = btc.history(period="1d")['Close'].iloc[-1]
            
            if df_h1.empty: return None

            # Volume Profile & RSI
            vah, val, poc = E11IntelligenceEngine.calculate_volume_profile(df_h1)
            rsi = E11IntelligenceEngine.calculate_rsi(df_h1['Close'])
            
            # Key Levels (Daily/Weekly)
            pdh, pdl = df_d['High'].iloc[-2], df_d['Low'].iloc[-2]
            pwh, pwl = df_d['High'].iloc[-5:].max(), df_d['Low'].iloc[-5:].min()
            
            # Sessions (Asia 06:00 - 15:00 KH)
            asia_df = df_h1.between_time('23:00', '08:00')
            asia_h = asia_df['High'].max() if not asia_df.empty else 0
            asia_l = asia_df['Low'].min() if not asia_df.empty else 0

            # Support & Resistance (Pivot points or swing levels)
            res = df_h1['High'].iloc[-24:].max()
            sup = df_h1['Low'].iloc[-24:].min()

            # Liquidity Pool (Order Blocks)
            bull_ob = df_h1[df_h1['Close'] < df_h1['Open']]['Low'].iloc[-1]
            bear_ob = df_h1[df_h1['Close'] > df_h1['Open']]['High'].iloc[-1]

            return {
                "p": round(df_h1['Close'].iloc[-1], 2),
                "h": round(df_h1['High'].iloc[-1], 2), "l": round(df_h1['Low'].iloc[-1], 2),
                "dxy": round(dxy_p, 2), "btc": round(btc_p, 2),
                "vah": vah, "val": val, "poc": poc,
                "pwh": round(pwh, 2), "pwl": round(pwl, 2),
                "pdh": round(pdh, 2), "pdl": round(pdl, 2),
                "asia_h": round(asia_h, 2), "asia_l": round(asia_l, 2),
                "sup": round(sup, 2), "res": round(res, 2),
                "bull_ob": round(bull_ob, 2), "bear_ob": round(bear_ob, 2),
                "rsi": rsi
            }
        except Exception as e:
            logger.error(f"Error: {e}")
            return None

async def send_full_report(context: ContextTypes.DEFAULT_TYPE):
    data = await E11IntelligenceEngine.get_market_data()
    if not data: return

    kh_tz = pytz.timezone('Asia/Phnom_Penh')
    now = datetime.datetime.now(kh_tz)
    
    # Session Logic
    h = now.hour
    sessions = []
    if 6 <= h < 15: sessions.append("🇯🇵 Tokyo")
    if 14 <= h < 23: sessions.append("🇬🇧 London")
    if 19 <= h or h < 4: sessions.append("🇺🇸 New York")
    sess_str = ", ".join(sessions) if sessions else "Pre-Market"

    # RSI Signal Logic
    if data['rsi'] <= 30: sig = "✅ ទិញ (Oversold)"
    elif data['rsi'] >= 70: sig = "🔽 លក់ (Overbought)"
    else: sig = "⏳ រង់ចាំ (Neutral)"

    report = (
        "🏦 *E11 INTELLIGENCE — XAUUSD*\n"
        f"🕐 {now.strftime('%Y-%m-%d %H:%M')} (KH) | \n"
        f" Market Open | ({sess_str})\n\n"
        "💰 *CURRENT MARKET PRICE:*\n"
        f"⚜️ Gold High: ${data['h']}\n"
        f"⚜️ Gold Low : ${data['l']}\n"
        f"💲 DXY Index: {data['dxy']}\n"
        f"🪙 BTC : ${data['btc']:,}\n\n"
        "📊 *VOLUME PROFILE (1H)*\n"
        f"  ⬆️ VAH : ${data['vah']}\n"
        f"  🎯 POC : ${data['poc']}\n"
        f"  ⬇️ VAL : ${data['val']}\n\n"
        "🔑 *Key Level:*\n"
        f"  💸 PWH : ${data['pwh']}\n"
        f"  💸 PWL : ${data['pwl']}\n"
        f"  💸 PDH : ${data['pdh']}\n"
        f"  💸 PDL : ${data['pdl']}\n"
        f"  🇯🇵 Asia H : ${data['asia_h']}\n"
        f"  🇯🇵 Asia L : ${data['asia_l']}\n"
        f"  ⚠️ Support : ${data['sup']}\n"
        f"  ⚠️ Resistance : ${data['res']}\n\n"
        "💰 *Liquidity Pool (1H):*\n"
        f"  🐂 Bullish OB : ${data['bull_ob']}\n"
        f"  🐻 Bearish OB : ${data['bear_ob']}\n\n"
        "🎯 *SIGNAL*\n"
        f"  Action : {sig}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "E11 Sniper Bot • ICT Sniper Logic"
    )
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=report, message_thread_id=TOPIC_ID, parse_mode="Markdown")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Phnom_Penh'))
    for hr in [8, 14, 19, 21]:
        scheduler.add_job(send_full_report, 'cron', hour=hr, minute=0, args=[app])
    app.add_handler(CommandHandler("report", lambda u, c: send_full_report(c)))
    async with app:
        await app.initialize(); await app.start()
        scheduler.start()
        await app.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
    
