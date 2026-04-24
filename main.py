import os, asyncio, yfinance as yf, pytz
from telegram.ext import ApplicationBuilder, CommandHandler
from datetime import time

# --- ១. CONFIG ---
TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID = os.environ.get('MY_CHAT_ID')
TOPIC_ID = os.environ.get('TOPIC_ID')

# --- ២. មុខងារទាញទិន្នន័យ ---
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

# --- ៣. មុខងារបញ្ជាម៉ាស៊ីន (FIXED LOOP) ---
async def start_bot():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('report', manual))
    
    if CHAT_ID:
        # បាញ់អូតូ ម៉ោង ៨ ព្រឹក
        app.job_queue.run_daily(send_msg, time(8, 0, tzinfo=pytz.timezone('Asia/Phnom_Penh')), days=(0,1,2,3,4))
        # បាញ់តេស្តភ្លាមៗ ១ គ្រាប់ពេលបើកម៉ាស៊ីន
        app.job_queue.run_once(send_msg, 5)
        
    async with app:
        await app.initialize()
        await app.start_polling()
        await asyncio.Event().wait() # រក្សាម៉ាស៊ីនឱ្យរត់ដោយមិនដាច់

if __name__ == '__main__':
    # ដំណោះស្រាយដាច់ខាតសម្រាប់ Error Line 104
    try:
        asyncio.run(start_bot())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(start_bot())
        else:
            loop.run_until_complete(start_bot())
            
