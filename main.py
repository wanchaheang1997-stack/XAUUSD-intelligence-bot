import os
import logging
import datetime
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import numpy as np
import ccxt
import time
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

BOT_TOKEN          = os.getenv("BOT_TOKEN")
MY_CHAT_ID         = os.getenv("MY_CHAT_ID")
TOPIC_ID           = os.getenv("TOPIC_ID")
TOPIC_ALERT        = os.getenv("TOPIC_ALERT")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")

last_alert_time = {}


# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCHING
# ══════════════════════════════════════════════════════════════════════════════

def get_exchange():
    return ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })


def fetch_ohlcv(timeframe="1h", limit=200):
    try:
        exchange = get_exchange()
        ohlcv    = exchange.fetch_ohlcv("PAXG/USDT", timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["Date"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        logger.warning(f"ccxt failed ({e}) — falling back to Twelve Data")
        return fetch_twelvedata(timeframe, limit)


def fetch_twelvedata(timeframe="1h", limit=200):
    interval_map = {"1m": "1min", "5m": "5min", "1h": "1h", "1d": "1day"}
    interval = interval_map.get(timeframe, "1h")
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol"    : "XAU/USD",
        "interval"  : interval,
        "outputsize": limit,
        "apikey"    : TWELVEDATA_API_KEY,
    }
    r    = requests.get(url, params=params, timeout=10)
    data = r.json()
    if "values" not in data:
        raise ValueError(f"Twelve Data error: {data.get('message', 'No data')}")
    df = pd.DataFrame(data["values"])
    df = df.rename(columns={
        "datetime": "Date", "open": "Open",
        "high": "High", "low": "Low", "close": "Close",
    })
    df["Date"]   = pd.to_datetime(df["Date"])
    df["Open"]   = df["Open"].astype(float)
    df["High"]   = df["High"].astype(float)
    df["Low"]    = df["Low"].astype(float)
    df["Close"]  = df["Close"].astype(float)
    df["Volume"] = 0.0
    df = df.sort_values("Date").reset_index(drop=True)
    return df


def get_live_price():
    try:
        exchange = get_exchange()
        ticker   = exchange.fetch_ticker("PAXG/USDT")
        return round(float(ticker["last"]), 2)
    except Exception:
        try:
            url    = "https://api.twelvedata.com/price"
            params = {"symbol": "XAU/USD", "apikey": TWELVEDATA_API_KEY}
            r      = requests.get(url, params=params, timeout=10)
            data   = r.json()
            if "price" in data:
                return round(float(data["price"]), 2)
        except Exception:
            pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
# INDICATORS
# ══════════════════════════════════════════════════════════════════════════════

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


def get_support_resistance(df):
    resistance = round(df["High"].rolling(10).max().iloc[-1], 2)
    support    = round(df["Low"].rolling(10).min().iloc[-1], 2)
    return support, resistance


# ══════════════════════════════════════════════════════════════════════════════
# SMC / ICT ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def get_daily_levels():
    df  = fetch_ohlcv("1d", 5)
    pdh = round(df["High"].iloc[-2], 2)
    pdl = round(df["Low"].iloc[-2], 2)
    pdc = round(df["Close"].iloc[-2], 2)
    return pdh, pdl, pdc


def get_session_levels(df_1h):
    now   = datetime.datetime.utcnow()
    today = now.date()
    sessions = {
        "Asia"  : (0,  8),
        "London": (7,  16),
        "NY"    : (13, 22),
    }
    result = {}
    for session, (start_h, end_h) in sessions.items():
        mask = (
            (df_1h["Date"].dt.date == today) &
            (df_1h["Date"].dt.hour >= start_h) &
            (df_1h["Date"].dt.hour < end_h)
        )
        session_df = df_1h[mask]
        if not session_df.empty:
            result[session] = {
                "high": round(session_df["High"].max(), 2),
                "low" : round(session_df["Low"].min(), 2),
            }
        else:
            result[session] = {"high": None, "low": None}
    return result


def detect_bos_choch(df_1h):
    highs      = df_1h["High"].rolling(5).max()
    lows       = df_1h["Low"].rolling(5).min()
    last_close = df_1h["Close"].iloc[-1]
    prev_high  = highs.iloc[-3]
    prev_low   = lows.iloc[-3]
    if last_close > prev_high:
        return "BOS_BULLISH", f"Price broke above ${round(prev_high, 2)}"
    elif last_close < prev_low:
        return "BOS_BEARISH", f"Price broke below ${round(prev_low, 2)}"
    else:
        return "NONE", "No structure break"


def detect_fvg(df):
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
    return fvg_bull, fvg_bear


def detect_order_block(df):
    ob_bull, ob_bear = None, None
    for i in range(1, len(df) - 1):
        curr      = df.iloc[i]
        next_c    = df.iloc[i + 1]
        body_curr = abs(curr["Close"] - curr["Open"])
        body_next = abs(next_c["Close"] - next_c["Open"])
        if curr["Close"] < curr["Open"] and next_c["Close"] > next_c["Open"] and body_next > body_curr * 1.5:
            ob_bull = (round(curr["Low"], 2), round(curr["High"], 2))
        if curr["Close"] > curr["Open"] and next_c["Close"] < next_c["Open"] and body_next > body_curr * 1.5:
            ob_bear = (round(curr["Low"], 2), round(curr["High"], 2))
    return ob_bull, ob_bear


def detect_sfp(df_5m, session_levels):
    last      = df_5m.iloc[-1]
    sfp_type  = None
    sfp_level = None
    for session, levels in session_levels.items():
        s_high = levels["high"]
        s_low  = levels["low"]
        if s_high and last["High"] > s_high and last["Close"] < s_high:
            sfp_type  = f"BEARISH SFP — {session} High Sweep"
            sfp_level = s_high
            break
        if s_low and last["Low"] < s_low and last["Close"] > s_low:
            sfp_type  = f"BULLISH SFP — {session} Low Sweep"
            sfp_level = s_low
            break
    return sfp_type, sfp_level


def get_volume_profile(df):
    if df["Volume"].sum() == 0:
        poc = round(df["Close"].median(), 2)
        vah = round(df["High"].quantile(0.75), 2)
        val = round(df["Low"].quantile(0.25), 2)
        return poc, vah, val
    price_min   = df["Low"].min()
    price_max   = df["High"].max()
    bins        = np.linspace(price_min, price_max, 50)
    vol_profile = np.zeros(len(bins) - 1)
    for _, row in df.iterrows():
        for j in range(len(bins) - 1):
            if bins[j] <= row["Close"] < bins[j + 1]:
                vol_profile[j] += row["Volume"]
                break
    poc_idx   = np.argmax(vol_profile)
    poc       = round((bins[poc_idx] + bins[poc_idx + 1]) / 2, 2)
    total_vol = vol_profile.sum()
    target    = total_vol * 0.70
    upper, lower = poc_idx, poc_idx
    covered      = vol_profile[poc_idx]
    while covered < target and (upper < len(vol_profile) - 1 or lower > 0):
        up_vol   = vol_profile[upper + 1] if upper < len(vol_profile) - 1 else 0
        down_vol = vol_profile[lower - 1] if lower > 0 else 0
        if up_vol >= down_vol:
            upper   += 1
            covered += up_vol
        else:
            lower   -= 1
            covered += down_vol
    vah = round((bins[upper] + bins[upper + 1]) / 2, 2)
    val = round((bins[lower] + bins[lower + 1]) / 2, 2)
    return poc, vah, val


def is_near_level(price, level, pct=0.002):
    if level is None:
        return False
    return abs(price - level) / level < pct


# ══════════════════════════════════════════════════════════════════════════════
# NEWS
# ══════════════════════════════════════════════════════════════════════════════

def get_economic_news():
    sources = [
        "https://www.fxstreet.com/rss/news",
        "https://www.forexlive.com/feed/news",
    ]
    headlines = []
    for url in sources:
        try:
            r    = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                title    = item.findtext("title", "").strip()
                keywords = ["gold", "xau", "fed", "rate", "inflation", "dollar", "fomc", "powell"]
                if any(k in title.lower() for k in keywords):
                    headlines.append(title)
                if len(headlines) >= 4:
                    break
        except Exception:
            continue
        if len(headlines) >= 4:
            break
    return headlines[:4] if headlines else ["No gold-related news found"]


# ══════════════════════════════════════════════════════════════════════════════
# SMC SIGNAL CHECKER
# ══════════════════════════════════════════════════════════════════════════════

async def smc_signal_check(bot):
    global last_alert_time
    try:
        today = datetime.datetime.utcnow().weekday()
        if today >= 5:
            return

        now   = datetime.datetime.utcnow()
        price = get_live_price()
        if not price:
            return

        df_1h = fetch_ohlcv("1h", 200)
        df_5m = fetch_ohlcv("5m", 100)

        pdh, pdl, pdc  = get_daily_levels()
        equilibrium    = round((pdh + pdl) / 2, 2)
        daily_bias     = "BULLISH" if price > equilibrium else "BEARISH"
        session_levels = get_session_levels(df_1h)
        bos_type, bos_reason = detect_bos_choch(df_1h)

        fvg_bull_5m, fvg_bear_5m = detect_fvg(df_5m)
        ob_bull_5m,  ob_bear_5m  = detect_order_block(df_5m)
        sfp_type, sfp_level      = detect_sfp(df_5m, session_levels)

        poc, vah, val = get_volume_profile(df_1h)
        near_vp = (
            is_near_level(price, poc) or
            is_near_level(price, vah) or
            is_near_level(price, val)
        )

        rsi_series = calculate_rsi(df_1h["Close"])
        rsi        = round(rsi_series.iloc[-1], 2)

        signal_type   = None
        signal_reason = []

        buy_conditions = [
            daily_bias == "BULLISH",
            "BULLISH" in bos_type,
            rsi < 65,
            near_vp,
            (
                (sfp_type and "BULLISH" in sfp_type) or
                (fvg_bull_5m and is_near_level(price, fvg_bull_5m[0])) or
                (ob_bull_5m  and is_near_level(price, ob_bull_5m[0]))
            ),
        ]

        sell_conditions = [
            daily_bias == "BEARISH",
            "BEARISH" in bos_type,
            rsi > 35,
            near_vp,
            (
                (sfp_type and "BEARISH" in sfp_type) or
                (fvg_bear_5m and is_near_level(price, fvg_bear_5m[1])) or
                (ob_bear_5m  and is_near_level(price, ob_bear_5m[1]))
            ),
        ]

        if all(buy_conditions):
            signal_type = "BUY"
            if sfp_type and "BULLISH" in sfp_type:
                signal_reason.append(sfp_type)
            if fvg_bull_5m:
                signal_reason.append(f"5m Bull FVG ${fvg_bull_5m[0]}–${fvg_bull_5m[1]}")
            if ob_bull_5m:
                signal_reason.append(f"5m Bull OB ${ob_bull_5m[0]}–${ob_bull_5m[1]}")
            signal_reason.append(bos_reason)
            signal_reason.append(f"Near VP Level (POC ${poc})")

        elif all(sell_conditions):
            signal_type = "SELL"
            if sfp_type and "BEARISH" in sfp_type:
                signal_reason.append(sfp_type)
            if fvg_bear_5m:
                signal_reason.append(f"5m Bear FVG ${fvg_bear_5m[0]}–${fvg_bear_5m[1]}")
            if ob_bear_5m:
                signal_reason.append(f"5m Bear OB ${ob_bear_5m[0]}–${ob_bear_5m[1]}")
            signal_reason.append(bos_reason)
            signal_reason.append(f"Near VP Level (POC ${poc})")

        if not signal_type:
            return

        last = last_alert_time.get(signal_type)
        if last and (now - last).seconds < 7200:
            return

        last_alert_time[signal_type] = now

        atr = round(df_1h["High"].tail(14).mean() - df_1h["Low"].tail(14).mean(), 2)
        if signal_type == "BUY":
            sl    = round(price - atr, 2)
            tp    = round(price + atr * 2, 2)
            emoji = "🟢"
        else:
            sl    = round(price + atr, 2)
            tp    = round(price - atr * 2, 2)
            emoji = "🔴"

        reason_text = "\n    ".join(signal_reason)
        now_str     = now.strftime("%Y-%m-%d %H:%M UTC")

        alert = f"""
⚡ *E11 SMC SIGNAL ALERT*
🕐 {now_str}

{emoji} *{signal_type} — XAUUSD*
💰 Price : *${price}*
🎯 TP    : ${tp}
🛑 SL    : ${sl}

📋 *Reason:*
    {reason_text}

📊 *Context:*
  Daily Bias : {daily_bias}
  1H BOS     : {bos_type}
  RSI (1H)   : {rsi}
  POC        : ${poc}
  VAH        : ${vah}
  VAL        : ${val}
  PDH        : ${pdh}
  PDL        : ${pdl}

━━━━━━━━━━━━━━━━━━━
_E11 Sniper Bot • Educational use only_
"""
        kwargs = {
            "chat_id"   : MY_CHAT_ID,
            "text"      : alert.strip(),
            "parse_mode": "Markdown",
        }
        if TOPIC_ALERT:
            kwargs["message_thread_id"] = int(TOPIC_ALERT)
        await bot.send_message(**kwargs)
        logger.info(f"⚡ SMC Alert sent: {signal_type} @ ${price}")

    except Exception as e:
        logger.error(f"❌ SMC check error: {e}", exc_info=True)


# ══════════════════════════════════════════════════════════════════════════════
# REPORT BUILDER
# ══════════════════════════════════════════════════════════════════════════════

async def build_report(bot, chat_id, topic_id=None):
    try:
        df_1h      = fetch_ohlcv("1h", 200)
        live_price = get_live_price()
        price      = live_price if live_price else round(df_1h["Close"].iloc[-1], 2)
        high       = round(df_1h["High"].iloc[-1], 2)
        low        = round(df_1h["Low"].iloc[-1], 2)

        last_candle_time = df_1h["Date"].iloc[-1].strftime("%Y-%m-%d %H:%M UTC")

        rsi_series         = calculate_rsi(df_1h["Close"])
        rsi                = round(rsi_series.iloc[-1], 2)
        macd, signal, hist = calculate_macd(df_1h["Close"])
        macd_val           = round(macd.iloc[-1], 2)
        signal_val         = round(signal.iloc[-1], 2)
        hist_val           = round(hist.iloc[-1], 2)

        support, resistance  = get_support_resistance(df_1h)
        trend_label, trend_r = get_trend(df_1h)
        pdh, pdl, pdc        = get_daily_levels()
        equilibrium          = round((pdh + pdl) / 2, 2)
        daily_bias           = "📈 BULLISH" if price > equilibrium else "📉 BEARISH"

        fvg_bull, fvg_bear   = detect_fvg(df_1h)
        ob_bull,  ob_bear    = detect_order_block(df_1h)
        bos_type, bos_reason = detect_bos_choch(df_1h)
        session_levels       = get_session_levels(df_1h)
        poc, vah, val        = get_volume_profile(df_1h)

        fvg_bull_str = f"${fvg_bull[0]} – ${fvg_bull[1]}" if fvg_bull else "None"
        fvg_bear_str = f"${fvg_bear[0]} – ${fvg_bear[1]}" if fvg_bear else "None"
        ob_bull_str  = f"${ob_bull[0]} – ${ob_bull[1]}"   if ob_bull  else "None"
        ob_bear_str  = f"${ob_bear[0]} – ${ob_bear[1]}"   if ob_bear  else "None"
        rsi_label    = "🔥 Overbought" if rsi > 70 else "🧊 Oversold" if rsi < 30 else "✅ Neutral"

        session_text = ""
        for s, lvl in session_levels.items():
            if lvl["high"]:
                session_text += f"  {s}: H ${lvl['high']} | L ${lvl['low']}\n"
        if not session_text:
            session_text = "  No session data yet\n"

        news       = get_economic_news()
        news_lines = "\n".join([f"  • {n}" for n in news])

        today        = datetime.datetime.utcnow().weekday()
        weekend_note = "\n⚠️ _Weekend — showing last available data_\n" if today >= 5 else ""

        report = f"""
🏦 *E11 INTELLIGENCE — XAUUSD*
🕐 {last_candle_time}{weekend_note}
💰 *PRICE*
  Current : *${price}*
  H1 High : ${high}  |  H1 Low : ${low}

📊 *DAILY BIAS*
  {daily_bias}
  EQ Level : ${equilibrium}

🔍 *1H STRUCTURE*
  {bos_type} — _{bos_reason}_
  Trend : {trend_label}

📐 *KEY LEVELS*
  PDH : ${pdh}  |  PDL : ${pdl}  |  PDC : ${pdc}
  Support    : ${support}
  Resistance : ${resistance}

🧠 *ICT CONCEPTS*
  Bull FVG : {fvg_bull_str}
  Bear FVG : {fvg_bear_str}
  Bull OB  : {ob_bull_str}
  Bear OB  : {ob_bear_str}

📊 *VOLUME PROFILE*
  POC : ${poc}
  VAH : ${vah}
  VAL : ${val}

⏰ *SESSION LEVELS*
{session_text}
📈 *INDICATORS*
  RSI (14)  : {rsi} {rsi_label}
  MACD      : {macd_val}
  Signal    : {signal_val}
  Histogram : {hist_val} {'▲' if hist_val > 0 else '▼'}

📰 *GOLD & MACRO NEWS*
{news_lines}

━━━━━━━━━━━━━━━━━━━
_E11 Sniper Bot • Educational use only_
"""
        kwargs = {
            "chat_id"   : chat_id,
            "text"      : report.strip(),
            "parse_mode": "Markdown",
        }
        if topic_id:
            kwargs["message_thread_id"] = int(topic_id)
        await bot.send_message(**kwargs)
        logger.info("✅ Report sent.")

    except Exception as e:
        logger.error(f"❌ Report error: {e}", exc_info=True)
        await bot.send_message(
            chat_id=chat_id,
            text=f"❌ Report failed:\n\n`{str(e)}`",
            parse_mode="Markdown",
        )


# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS
# ══════════════════════════════════════════════════════════════════════════════

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

async def instant_report(update: Update, con
