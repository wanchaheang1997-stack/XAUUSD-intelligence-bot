import os
import logging
import datetime
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN  = os.getenv("BOT_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
TOPIC_ID   = os.getenv("TOPIC_ID")


# ── Market Data ────────────────────────────────────────────────────────────────

def get_xauusd_data():
    ticker = yf.Ticker("GC=F")
    df = ticker.history(period="10d", interval="1h")
    if df.empty:
        raise ValueError("No market data available from yfinance")
    return df


# ── Indicators ─────────────────────────────────────────────────────────────────

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = -delta.clip(upper=0).rolling(period).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(series):
    ema12     = series.ewm(span=12, adjust=False).mean()
    ema26     = series.ewm(span=26, adjust=False).mean()
    macd      = ema12 - ema26
    signal    = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    return macd, signal, histogram


# ── Support & Resistance ───────────────────────────────────────────────────────

def get_support_resistance(df):
    resistance = round(df["High"].rolling(10).max().iloc[-1], 2)
    support    = round(df["Low"].rolling(10).min().iloc[-1], 2)
    return support, resistance


# ── ICT Levels ─────────────────────────────────────────────────────────────────

def get_ict_levels(df):
    daily = yf.Ticker("GC=F").history(period="10d", interval="1d")

    pdh = round(daily["High"].iloc[-2], 2)
    pdl = round(daily["Low"].iloc[-2], 2)
    pdc = round(daily["Close"].iloc[-2], 2)

    eq_high = round(df["High"].tail(20).max(), 2)
    eq_low  = round(df["Low"].tail(20).min(), 2)

    fvg_bull, fvg_bear = None, None
    for i in range(2, len(df)):
        c0_high = df["High"].iloc[i - 2]
        c2_low  = df["Low"].iloc[i]
        c0_low  = df["Low"].iloc[i - 2]
        c2_high = df["High"].iloc[i]
        if c2_low > c0_high:
            fvg_bull = (round(c0_high, 2), round(c2_low, 2))
        if c2_high < c0_low:
            fvg_bear = (round(c2_high, 2), round(c0_low, 2))

    return pdh, pdl, pdc, eq_high, eq_low, fvg_bull, fvg_bear


# ── Liquidity ──────────────────────────────────────────────────────────────────

def get_liquidity(df, price):
    daily       = yf.Ticker("GC=F").history(period="10d", interval="1d")
    pdh         = round(daily["High"].iloc[-2], 2)
    pdl         = round(daily["Low"].iloc[-2], 2)
    spread      = round(pdh - pdl, 2)
    equilibrium = round((pdh + pdl) / 2, 2)
    ext_buy     = f"${pdh + 2:.2f}+"
    ext_sell    = f"Below ${pdl - 2:.2f}"
    int_status  = (
        "Price above EQ — Seeking Buy-Side"
        if price > equilibrium
        else "Price below EQ — Seeking Sell-Side"
    )
    return ext_buy, ext_sell, equilibrium, int_status, spread


# ── Trend ──────────────────────────────────────────────────────────────────────

def get_trend(df):
    ema20 = df["Close"].ewm(span=20).mean().iloc[-1]
    ema50 = df["Close"].ewm(span=50).mean().iloc[-1]
    price = df["Close"].iloc[-1]
    if price > ema20 > ema50:
        return "📈 BULLISH", "Price above EMA20 & EMA50"
    elif price < ema20 < ema50:
        return "📉 BEARISH", "Price below EMA20 & EMA50"
    else:
        return "⚖️ RANGING", "Mixed EMA signals"


# ── Signal ─────────────────────────────────────────────────────────────────────

def get_signal(rsi, macd_val, signal_val, trend):
    if "BULLISH" in trend and rsi < 70 and macd_val > signal_val:
        return "🟢 BUY", "Bullish trend + RSI healthy + MACD crossover"
    elif "BEARISH" in trend and rsi > 30 and macd_val < signal_val:
        return "🔴 SELL", "Bearish trend + RSI healthy + MACD crossunder"
    elif rsi > 75:
        return "⚠️ OVERBOUGHT", "RSI extreme — avoid buying"
    elif rsi < 25:
        return "⚠️ OVERSOLD", "RSI extreme — avoid selling"
    else:
        return "⏳ WAIT", "No clear signal — stay patient"


# ── News ───────────────────────────────────────────────────────────────────────

def get_economic_news():
    try:
        key = os.getenv("GNEWS_API_KEY", "")
        if not key:
            return ["Add GNEWS_API_KEY to Railway Variables for live news"]
        r = requests.get(
            "https://gnews.io/api/v4/search",
            params={"q": "gold XAUUSD federal reserve", "lang": "en", "max": 3, "token": key},
            timeout=5,
        )
        if r.status_code == 200:
            return [a["title"] for a in r.json().get("articles", [])[:3]]
    except Exception:
        pass
    return ["News unavailable"]


# ── Report Builder ─────────────────────────────────────────────────────────────

async def build_report(bot, chat_id, topic_id=None):
    try:
        df    = get_xauusd_data()
        price = round(df["Close"].iloc[-1], 2)
        high  = round(df["High"].iloc[-1], 2)
        low   = round(df["Low"].iloc[-1], 2)

        # Use last candle timestamp (shows Friday time on weekends)
        last_candle_time = df.index[-1].strftime("%Y-%m-%d %H:%M UTC")

        rsi_series         = calculate_rsi(df["Close"])
        rsi                = round(rsi_series.iloc[-1], 2)
        macd, signal, hist = calculate_macd(df["Close"])
        macd_val           = round(macd.iloc[-1], 2)
        signal_val         = round(signal.iloc[-1], 2)
        hist_val           = round(hist.iloc[-1], 2)

        support, resistance             = get_support_resistance(df)
        trend_label, trend_reason       = get_trend(df)
        signal_label, sig_reason        = get_signal(rsi, macd_val, signal_val, trend_label)
        pdh, pdl, pdc, eq_high, eq_low, fvg_bull, fvg_bear = get_ict_levels(df)
        ext_buy, ext_sell, equilibrium, int_status, spread  = get_liquidity(df, price)

        news       = get_economic_news()
        news_lines = "\n".join([f"  • {n}" for n in news])

        fvg_bull_str = f"${fvg_bull[0]} – ${fvg_bull[1]}" if fvg_bull else "None detected"
        fvg_bear_str = f"${fvg_bear[0]} – ${fvg_bear[1]}" if fvg_bear else "None detected"

        rsi_label = "🔥 Overbought" if rsi > 70 else "🧊 Oversold" if rsi < 30 else "✅ Neutral"

        report = f"""
🏦 *E11 INTELLIGENCE — XAUUSD*
🕐 Data as of: {last_candle_time}

💰 *LIVE PRICE*
  Price : *${price}*
  High  : ${high}
  Low   : ${low}

📊 *TREND*
  {trend_label}
  _{trend_reason}_

📐 *SUPPORT & RESISTANCE*
  🟢 Support    : ${support}
  🔴 Resistance : ${resistance}

🧠 *ICT KEY LEVELS*
  PDH : ${pdh}
  PDL : ${pdl}
  PDC : ${pdc}
  Equal Highs : ${eq_high}
  Equal Lows  : ${eq_low}
  Bull FVG : {fvg_bull_str}
  Bear FVG : {fvg_bear_str}

💧 *LIQUIDITY*
  🔵 External Buy-Side  : {ext_buy}
  🔴 External Sell-Side : {ext_sell}
  ⚖️ Equilibrium        : ${equilibrium}
  📍 Internal           : {int_status}
  📏 Day Range          : ${spread}

📈 *INDICATORS*
  RSI (14)  : {rsi} {rsi_label}
  MACD      : {macd_val}
  Signal    : {signal_val}
  Histogram : {hist_val} {'▲' if hist_val > 0 else '▼'}

🎯 *SIGNAL*
  {signal_label}
  _{sig_reason}_

📰 *MARKET NEWS*
{news_lines}

━━━━━━━━━━━━━━━━━━━
_E11 Sniper Bot • Educational use only_
"""

        kwargs = {"chat_id": chat_id, "text": report.strip(), "parse_mode": "Markdown"}
        if topic_id:
            kwargs["message_thread_id"] = int(topic_id)

        await bot.send_message(**kwargs)
        logger.info("✅ Report sent.")

    except Exception as e:
        logger.error(f"❌ Report error: {e}", exc_info=True)
        try:
            await bot.send_message(chat_id=chat_id, text=f"❌ Report error: {e}")
        except Exception:
            pass


# ── Handlers ───────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *E11 Sniper Bot is live!*\n\n"
        "/report — Full XAUUSD market report\n"
        "/help   — Show all commands",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Commands:*\n"
        "/start  — Welcome\n"
        "/help   — This menu\n"
        "/report — Live XAUUSD intelligence report",
        parse_mode="Markdown",
    )


async def instant_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.datetime.utcnow().weekday()
    if today >= 5:
        await update.message.reply_text(
            "📅 *Weekend Mode*\n"
            "_(Markets closed — showing last available Friday data)_",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("⏳ Analyzing XAUUSD market...")
    await build_report(context.bot, update.effective_chat.id, TOPIC_ID)


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Unknown command. Try /help.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        raise EnvironmentError("BOT_TOKEN is not set!")
    if not MY_CHAT_ID:
        raise EnvironmentError("MY_CHAT_ID is not set!")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start",  start))
    application.add_handler(CommandHandler("help",   help_command))
    application.add_handler(CommandHandler("report", instant_report))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        build_report,
        trigger="cron",
        hour=9,
        minute=0,
        args=[application.bot, MY_CHAT_ID, TOPIC_ID],
        id="daily_report",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    logger.info("🚀 E11 Sniper Bot Is Running... Waiting for commands.")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
