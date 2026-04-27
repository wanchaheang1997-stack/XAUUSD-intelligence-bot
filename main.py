import os
import logging
import datetime
import asyncio
import yfinance as yf
import pandas as pd
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- SYSTEM LOGGING ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIG & ENV ---
BOT_TOKEN   = os.getenv("BOT_TOKEN")
MY_CHAT_ID  = os.getenv("MY_CHAT_ID")
TOPIC_ID    = os.getenv("TOPIC_ID")
ALERT_TOPIC = "3"

# --- CORE ICT & SESSION LOGIC ---
class ICTEngine:
    @staticmethod
    async def get_analysis():
        try:
            gold = yf.Ticker("GC=F")
            dxy = yf.Ticker("DX-Y.NYB")
            
            # ទាញយកទិន្នន័យ 1H
            df = gold.history(period="15d", interval="1h")
            d_df = dxy.history(period="5d", interval="1h")
            
            if df.empty: return None

            last_price = round(df['Close'].iloc[-1], 2)
            
            # 1. Market Structure (1H)
            recent_high = df['High'].iloc[-48:].max()
            recent_low = df['Low'].iloc[-48:].min()
            trend = "⚖️ RANGING"
            if last_price > recent_high * 0.999: trend = "🐂 BULLISH (BOS Up)"
            elif last_price < recent_low * 1.001: trend = "🐻 BEARISH (BOS Down)"

            # 2. Bullish & Bearish Order Blocks (1H)
            # Bullish OB: ទៀនក្រហមចុងក្រោយមុនការឡើងខ្លាំង
            bull_ob_df = df[df['Close'] < df['Open']]
            bull_ob = round(bull_ob_df['Low'].iloc[-1], 2) if not bull_ob_df.empty else 0
            
            # Bearish OB: ទៀនខៀវចុងក្រោយមុនការចុះខ្លាំង
            bear_ob_df = df[df['Close'] > df['Open']]
            bear_ob = round(bear_ob_df['High'].iloc[-1], 2) if not bear_ob_df.empty else 0

            # 3. Liquidity & Equilibrium
            bsl = round(df['High'].iloc[-100:].max(), 2)
            ssl = round(df['Low'].iloc[-100:].min(), 2)
            eq = round((bsl + ssl) / 2, 2)

            return {
                "price": last_price, "trend": trend, "eq": eq,
                "bull_ob": bull_ob, "bear_ob": bear_ob,
                "dxy": round(d_df['Close'].iloc[-1], 2)
            }
        except Exception as e:
            logger.error(f"Logic Error: {e}")
            return None

# --- REPORT GENERATOR ---
async def send_report(context: ContextTypes.DEFAULT_TYPE, is_scheduled=False):
    data = await ICTEngine.get_analysis()
    if not data: return

    kh_tz = pytz.timezone('Asia/Phnom_Penh')
    now = datetime.datetime.now(kh_tz)
    hour = now.hour
    
    # 1. Market Sessions Logic (Tokyo, London, New York)
    # Tokyo: 06:00 - 15:00 KH | London: 14:00 - 23:00 KH | NY: 19:00 - 04:00 KH
    sessions = []
    if 6 <= hour < 15: sessions.append("🇯🇵 Tokyo")
    if 14 <= hour < 23: sessions.append("🇬🇧 London")
    if 19 <= hour or hour < 4: sessions.append("🇺🇸 New York")
    
    current_sessions = " | ".join(sessions) if sessions else "⏳ Pre-Market"
    market_status = "🟢 Market Open" if now.weekday() < 5 else "⚠️ Weekend"

    # 2. Signal Confluence
    signal = "⏳ WAIT"
    if "BULLISH" in data['trend'] and data['price'] < data['eq']:
        signal = "🚀 BUY (Discount Zone)"
    elif "BEARISH" in data['trend'] and data['price'] > data['eq']:
        signal = "📉 SELL (Premium Zone)"

    report = (
        "🛡️ *CORE SYSTEM MONITORING*\n"
        "Check Economic Calendar & DXY. Trade with the flow, avoid traps.\n\n"
        "🏦 *E11 INTELLIGENCE — XAUUSD*\n"
        f"🕐 {now.strftime('%Y-%m-%d %H:%M')} (KH)\n"
        f"{market_status} | {current_sessions}\n\n"
        "💰 *PRICE*\n"
        f"  Current : ${data['price']}\n"
        f"  DXY Index : {data['dxy']}\n\n"
        "📊 *MARKET STRUCTURE (1H)*\n"
        f"  Trend : {data['trend']}\n"
        f"  EQ Level : ${data['eq']}\n\n"
        "🧠 *ICT KEY LEVELS (1H)*\n"
        f"  🐂 Bullish OB : ${data['bull_ob']}\n"
        f"  🐻 Bearish OB : ${data['bear_ob']}\n\n"
        "🎯 *SIGNAL*\n"
        f"  Action : {signal}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "E11 Sniper Bot • ICT Sniper Logic"
    )

    target = ALERT_TOPIC if is_scheduled else TOPIC_ID
    try:
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=report, message_thread_id=target, parse_mode="Markdown")
    except Exception as e: logger.error(f"Send Error: {e}")

# --- MAIN RUNNER ---
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Phnom_Penh'))

    # Schedule តាមម៉ោងសំខាន់ៗ (Tokyo, London, NY Open)
    for hr in [8, 14, 19, 21]:
        scheduler.add_job(send_report, 'cron', hour=hr, minute=0, args=[app])

    app.add_handler(CommandHandler("report", lambda u, c: send_report(c)))
    
    async with app:
        await app.initialize()
        await app.start()
        scheduler.start()
        await app.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
    
