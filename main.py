import os, asyncio, yfinance as yf, pytz
from telegram.ext import ApplicationBuilder, CommandHandler
from datetime import time

# --- ១. CONFIG ---
TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('MY_CHAT_ID')
TOPIC_ID = os.environ.get('TOPIC_ID')

async def get_report():
    try:
        g = yf.download('GC=F', period='1d', interval='1m', progress=False)
        p = float(g['Close'].iloc[-1])
        return f"🏛 **E11 INTELLIGENCE**\n💰 XAUUSD: `${p:.2f}`\n✅ Sniper Bot រស់ហើយមេ!"
    except: return "⚠️ Error data!"

async def send_auto(context):
    """មុខងារបាញ់អូតូ"""
    tid = int(TOPIC_ID) if TOPIC_ID else None
    await context.bot.send_message(chat_id=CHAT_ID, text=await get_report(), parse_mode='Markdown', message_thread_id=tid)

async def manual(u, c):
    """Command /report"""
    tid = u.effective_message.message_thread_id if u.effective_message.is_topic_message else None
    await u.message.reply_text(await get_report(), parse_mode='Markdown', message_thread_id=tid)

def main():
    if not TOKEN: return
    # បង្កើត Application (ប្រើរបៀបសាមញ្ញបំផុតដើម្បីជៀសវាង Loop Error)
    app = ApplicationBuilder().token(TOKEN).build()
    
    app.add_handler(CommandHandler('report', manual))
    
    if CHAT_ID:
        # បាញ់អូតូ រៀងរាល់ព្រឹកម៉ោង ៨ (ម៉ោងកម្ពុជា)
        app.job_queue.run_daily(send_auto, time(8, 0, tzinfo=pytz.timezone('Asia/Phnom_Penh')), days=(0,1,2,3,4))
        # បាញ់តេស្ត ១ គ្រាប់ភ្លាមៗ ៥ វិនាទីក្រោយបើក Bot
        app.job_queue.run_once(send_auto, 5)

    print("🚀 Sniper Bot is Online & Polling...")
    # នេះជាថ្នាំព្យាបាល Error line 104/649៖ ប្រើ run_polling ផ្ទាល់
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
    
