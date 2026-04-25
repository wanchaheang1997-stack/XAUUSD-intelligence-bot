import os
import logging
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


async def send_auto_report(bot):
    try:
        kwargs = {
            "chat_id"   : MY_CHAT_ID,
            "text"      : "📊 Daily Report — all systems normal.",
            "parse_mode": "Markdown",
        }
        if TOPIC_ID:
            kwargs["message_thread_id"] = int(TOPIC_ID)
        await bot.send_message(**kwargs)
        logger.info("✅ Daily report sent.")
    except Exception as e:
        logger.error(f"❌ Report failed: {e}", exc_info=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bot is running!\nUse /help to see commands."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Available Commands:*\n"
        "/start — Start the bot\n"
        "/help — Show this message\n"
        "/report — Get an instant report",
        parse_mode="Markdown",
    )


async def instant_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Sending report...")
    await send_auto_report(context.bot)
    await update.message.reply_text("✅ Done!")


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Unknown command. Try /help.")


def main():
    if not BOT_TOKEN:
        raise EnvironmentError("BOT_TOKEN is not set!")
    if not MY_CHAT_ID:
        raise EnvironmentError("MY_CHAT_ID is not set!")

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # ── Handlers (order matters — catch-all MUST be last) ─────────────────────
    application.add_handler(CommandHandler("start",  start))
    application.add_handler(CommandHandler("help",   help_command))
    application.add_handler(CommandHandler("report", instant_report))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # ── Scheduler ─────────────────────────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        send_auto_report,
        trigger="cron",
        hour=9,
        minute=0,
        args=[application.bot],
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
