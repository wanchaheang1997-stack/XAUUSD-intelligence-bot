import os
import logging
import datetime
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- SYSTEM LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIG & ENV ---
BOT_TOKEN   = os.getenv("BOT_TOKEN")
MY_CHAT_ID  = os.getenv("MY_CHAT_ID")
TOPIC_ID    = os.getenv("TOPIC_ID")
ALERT_TOPIC = "3"

# --- CORE ICT LOGIC ENGINE ---
class ICTAnalyzer:
    def __init__(self, symbol="GC=F"):
        self.symbol = symbol

    async def fetch_data(self):
        try:
            # ទាញយកទិន្នន័យមាស និង DXY
            gold = yf.Ticker(self.symbol)
            dxy = yf.Ticker("DX-Y.NYB")
            
            df = gold.history(period="20d", interval="1h")
            d_df = dxy.history(period="5d", interval="1h")
            
            if df.empty or d_df.empty: return None
            return df, d_df
        except Exception as e:
            logger.error(f"Fetch Error: {e}")
            return None

    def get_market_structure(self, df):
        # រក BOS/CHOCH តាមរយៈ Swing High/Low
        recent_high = df['High'].iloc[-50:-1].max()
        recent_low = df['Low'].iloc[-50:-1].min()
        last_close = df['Close'].iloc[-1]
        
        if last_close > recent_high: return "🐂 BULLISH (BOS Up)"
        if last_close < recent_low: return "🐻 BEARISH (BOS Down)"
        return "⚖️ RANGING"

    def find_levels(self, df):
        # គណនា Fair Value Gap (FVG)
        fvg = "None"
        for i in range(len(df)-3, len(df)-1):
            if df['Low'].iloc[i+1] > df['High'].iloc[i-1]: # Bullish FVG
                fvg = f"{df['High'].iloc[i-1]:.2f} - {df['Low'].iloc[i+1]:.2f}"
            elif df['High'].iloc[i+1] < df['Low'].iloc[i-1]: # Bearish FVG
                fvg = f"{df['Low'].iloc[i-1]:.2f} - {df['High'].iloc[i+1]:.2f}"

        # គណនា Order Block (OB)
        # ទៀនបញ្ច្រាសចុងក្រោយមុនការផ្ទុះតម្លៃ
        ob = df['Low'][df['Close'] < df['Open']].iloc[-1]
        
        # Liquidity & Equilibrium
        bsl = df['High'].iloc[-100:].max()
        ssl = df['Low'].iloc[-100:].min()
        eq = (bsl + ssl) / 2
        
        return {"fvg": fvg, "ob": ob, "bsl": bsl, "ssl": ssl, "eq": eq}

# --- REPORT GENERATOR ---
async def generate_ict_report(context: ContextTypes.DEFAULT_TYPE, is_scheduled=False):
    analyzer = ICTAnalyzer()
    data = await analyzer.fetch_data()
    if not data: return
    
    df, dxy_df = data
    analysis = analyzer.find_levels(df)
    trend = analyzer.get_market_structure(df)
    
    kh_tz = pytz.timezone('Asia/Phnom_Penh')
    now = datetime.datetime.now(kh_tz)
    
    # Session Detection
    hour = now.hour
    session = "☕ Asian"
    if 14 <= hour < 18: session = "💂 London Killzone"
    elif 19 <= hour < 23: session = "🗽 NY Killzone"
    
    # Market Status
    market_status = "🟢 Market Open" if now.weekday() < 5 else "⚠️ Weekend (Static Data)"
    
    # DXY Context
    dxy_price = dxy_df['Close'].iloc[-1]
    dxy_bias = "Weak (Bullish for Gold)" if dxy_price < dxy_df['Close'].iloc[-5] else "Strong (Bearish for Gold)"

    # Signal Confluence
    signal = "⏳ WAIT"
    last_price = df['Close'].iloc[-1]
    if "BULLISH" in trend and last_price < analysis['eq'] and dxy_price < dxy_df['Close'].iloc[-2]:
        signal = "🚀 BUY (Discount + DXY Weak)"
    elif "BEARISH" in trend and last_price > analysis['eq'] and dxy_price > dxy_df['Close'].iloc[-2]:
        signal = "📉 SELL (Premium + DXY Strong)"

    report = (
        "🛡️ *CORE SYSTEM MONITORING*\n"
        "Check Economic Calendar & DXY before entry. Align bias with HTF.\n\n"
        "🏦 *E11 INTELLIGENCE — XAUUSD*\n"
        f"🕐 {now.strftime('%Y-%m-%d %H:%M')} (KH)\n"
        f"{market_status} | {session}\n\n"
        "💰 *PRICE*\n"
        f"  Current : ${last_price:.2f}\n"
        f"  DXY Index : {dxy_price:.2f} ({dxy_bias})\n\n"
        "📊 *MARKET STRUCTURE*\n"
        f"  Trend : {trend}\n"
        f"  EQ Level : ${analysis['eq']:.2f}\n\n"
        "🧠 *ICT KEY LEVELS*\n"
        f"  Order Block : ${analysis['ob']:.2f}\n"
        f"  FVG Zone    : {analysis['fvg']}\n\n"
        "🎯 *SIGNAL*\n"
        f"  Action : {signal}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "E11 Sniper Bot • Sonnet 4.6 Adaptive"
    )

    target = ALERT_TOPIC if is_scheduled else TOPIC_ID
    await context.bot.send_message(
        chat_id=MY_CHAT_ID, 
        text=report, 
        message_thread_id=target, 
        parse_mode="Markdown"
    )

# --- MAIN RUNNER ---
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Phnom_Penh'))

    # Schedule: 8AM, 2PM (London), 7PM & 9PM (NY)
    for hr in [8, 14, 19, 21]:
        scheduler.add_job(generate_ict_report, 'cron', hour=hr, minute=0, args=[app])

    app.add_handler(CommandHandler("report", lambda u, c: generate_ict_report(c)))
    
    async with app:
        await app.initialize()
        await app.start()
        scheduler.start()
        logger.info("✅ E11 Sniper Bot is Live with ICT Logic")
        await app.updater.start_polling(drop_pending_updates=True)
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
    
