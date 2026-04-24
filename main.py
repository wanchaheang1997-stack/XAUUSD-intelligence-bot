import os, asyncio, yfinance as yf, pytz
from telegram.ext import ApplicationBuilder, CommandHandler
from datetime import time

# --- CONFIG ---
TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('MY_CHAT_ID')
TOPIC_ID = os.environ.get('TOPIC_ID')

async def get_report():
    try:
        g = yf.download('GC=F', period='1d', interval='1m', progress=False)
        p = float(g['Close'].iloc[-1])
        return f"🏛 **E11 INTELLIGENCE**\n💰 XAUUSD: `${p:.2f}`\n✅ Sniper Active!"
    except: return "⚠️ Error data!"

async def send_msg(context):
    tid = int(TOPIC_ID) if TOPIC_ID else None
    await context.bot.send_message(chat_id=CHAT_ID, text=await get_report(), parse_mode='Markdown', message_thread_id=tid)

async def manual(u, c):
    tid = u.effective_message.message_thread_id if u.effective_message.is_topic_message else None
    await u.message.reply_text(await get_report(), parse_mode='Markdown', message_thread_id=tid)

def main():
    if not TOKEN: return
    # បង្កើត Application តាមរបៀបស្តង់ដារដែលមិនងាយ Crash
    app = ApplicationBuilder().token(TOKEN).build()
    
    # បន្ថែម Command
    app.add_handler(CommandHandler('report', manual))
    
    # កំណត់ម៉ោងបាញ់អូតូ (៨ ព្រឹក) និងបាញ់តេស្តភ្លាមៗ (ក្រោយ ៥ វិនាទី)
    if CHAT_ID:
        app.job_queue.run_daily(send_msg, time(8, 0, tzinfo=pytz.timezone('Asia/Phnom_Penh')), days=(0,1,2,3,4))
        app.job_queue.run_once(send_msg, 5)

    print("🚀 E11 Sniper is starting...")
    # រត់ Bot តាមរបៀបសាមញ្ញបំផុតដើម្បីជៀសវាង Error Loop
    app.run_polling()

if __name__ == '__main__':
    main()
    
