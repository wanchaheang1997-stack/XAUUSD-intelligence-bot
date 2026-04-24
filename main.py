import os
import logging
import asyncio
import yfinance as yf
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- ១. ការកំណត់ CONFIG (ទាញចេញពី Variables/Secrets) ---
TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('MY_CHAT_ID')
TOPIC_ID = os.environ.get('TOPIC_ID') # លេខបន្ទប់ Report

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ២. មុខងារទាញទិន្នន័យមាស (Market Intelligence) ---
def get_intelligence_report():
    try:
        # ទាញយកទិន្នន័យ Gold (GC=F) និង DXY
        gold = yf.download('GC=F', period='5d', interval='1h', progress=False)
        dxy = yf.download('DX-Y.NYB', period='5d', interval='1h', progress=False)
        
        curr_p = float(gold['Close'].iloc[-1])
        pdh = float(gold['High'].iloc[-2])
        pdl = float(gold['Low'].iloc[-2])
        dxy_val = float(dxy['Close'].iloc[-1])
        
        bias = "BULLISH 🚀" if curr_p > pdh else "BEARISH 📉" if curr_p < pdl else "NEUTRAL ↔️"
        
        return (
            f"🏛 *E11 GLOBAL INTELLIGENCE V5*\n"
            f"⏰ `{datetime.now(pytz.timezone('Asia/Phnom_Penh')).strftime('%H:%M')} (Cambodia)`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *XAUUSD:* `${curr_p:.2f}`\n"
            f"📊 *BIAS:* {bias}\n\n"
            f"🌍 *CONTEXT:*\n"
            f"• DXY Index: `{dxy_val:.2f}`\n"
            f"• PDH: `${pdh:.2f}` | PDL: `${pdl:.2f}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ _Master Sniper System Active_"
        )
    except Exception as e:
        logger.error(f"Data Error: {e}")
        return "⚠️ មិនអាចទាញទិន្នន័យមាសបានទេ!"

# --- ៣. មុខងារបាញ់សារ (Bot Actions) ---

# បាញ់អូតូ (បាញ់ចំ Topic ID ដែលមេបានកំណត់)
async def send_auto_report(application):
    if CHAT_ID:
        try:
            report = get_intelligence_report()
            # បើមាន Topic ID វានឹងបាញ់ចូលបន្ទប់នោះ បើអត់ទេវានឹងបាញ់ចូល General
            await application.bot.send_message(
                chat_id=CHAT_ID,
                text=report,
                parse_mode='Markdown',
                message_thread_id=int(TOPIC_ID) if TOPIC_ID else None
            )
            logger.info("✅ Auto-report sent successfully.")
        except Exception as e:
            logger.error(f"❌ Auto-report failed: {e}")

# Command /report (ឆ្លើយតបក្នុង Topic ដើមវិញភ្លាម)
async def manual_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    report = get_intelligence_report()
    thread_id = update.effective_message.message_thread_id if update.effective_message.is_topic_message else None
    await update.message.reply_text(
        report, 
        parse_mode='Markdown', 
        message_thread_id=thread_id
    )

# --- ៤. ចំណុចចាប់ផ្ដើម (Main Engine) ---
async def main():
    if not TOKEN:
        logger.error("❌ រកមិនឃើញ BOT_TOKEN ទេ! សូមឆែក Variables។")
        return

    application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler('report', manual_report))
    
    # កំណត់ម៉ោងបាញ់ (ឧទាហរណ៍៖ ច័ន្ទ-សុក្រ ម៉ោង ៨:០០ ព្រឹក កម្ពុជា)
    scheduler = AsyncIOScheduler(timezone="Asia/Phnom_Penh")
    scheduler.add_job(send_auto_report, 'cron', day_of_week='mon-fri', hour=8, minute=0, args=[application])
    scheduler.start()
    
    logger.info("🚀 E11 Sniper Bot Is Running... Waiting for commands.")

    async with application:
        await application.initialize()
        await application.start_polling()
        while True:
            await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Bot stopped.")
        
