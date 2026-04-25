import logging
import os
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler
from apscheduler.schedulers.asyncio import AsyncioScheduler

# 1. ការកំណត់ Logging ដើម្បីងាយស្រួលឆែក Error ក្នុង Railway
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ទាញយក Token និង Chat ID ពី Variables របស់ Railway
TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")

# 2. បង្កើត Function សម្រាប់បាញ់ Report អូតូ
async def send_auto_report(context):
    # កន្លែងនេះមេអាចដាក់ Logic វិភាគមាស XAUUSD របស់មេ
    message = "🚀 **E11 Sniper Report**\n\nវិភាគមាសថ្ងៃនេះ៖ [ដាក់ Logic របស់មេនៅទីនេះ]"
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=message, parse_mode='Markdown')
    logger.info("Auto report sent successfully!")

# 3. បង្កើត Command /start
async def start(update, context):
    await update.message.reply_text("ជម្រាបសួរមេ! E11 Sniper Bot រួចរាល់សម្រាប់បាញ់ Signal ហើយ។")

async def main():
    # បង្កើត Application (ជំនួស start_polling ដោយ run_polling ក្នុង version ថ្មី)
    application = ApplicationBuilder().token(TOKEN).build()

    # បន្ថែម Command Handlers
    application.add_handler(CommandHandler("start", start))

    # 4. កំណត់ Scheduler សម្រាប់បាញ់ Report រាល់ថ្ងៃ (ឧទាហរណ៍៖ ម៉ោង ៨ ព្រឹក)
    scheduler = AsyncioScheduler()
    # មេអាចប្តូរម៉ោងនៅទីនេះ (hour=8, minute=0)
    scheduler.add_job(send_auto_report, 'cron', hour=8, minute=0, args=[application])
    scheduler.start()

    logger.info("🚀 E11 Sniper Bot Is Running... Waiting for commands.")

    # ចំណុចសំខាន់៖ ប្រើ run_polling() ដើម្បីឱ្យ Bot ដំណើរការជាប់រហូត
    # វានឹងគ្រប់គ្រង loop ឱ្យយើងដោយអូតូ
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # រក្សាឱ្យ Bot ដើរជាប់រហូត (Idle)
    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
        
