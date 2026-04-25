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

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Environment Variables ──────────────────────────────────────────────────────
BOT_TOKEN  = os.getenv("BOT_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
TOPIC_ID   = os.getenv("TOPIC_ID")   # Optional — only set if using a forum topic

# ── Scheduled Job ─────────────────────────────────────────────────────────────
async def send_daily_report(bot):
    """
    Sends the daily report.
    - If TOPIC_ID is set, sends to that specific forum thread.
    - Wrapped in try/except so a failure never crashes the bot.
    """
    try:
        kwargs = {
            "chat_id"    : MY_CHAT_ID,
            "text"       : "📊 *Daily Report*\n\nYour scheduled report is ready!",
            "parse_mode" : "Markdown",
        }
        # Only add message_thread_id if TOPIC_ID is actually configured
        if TOPIC_ID:
            kwargs["message_thread_id"] = int(TOPIC_ID)

        await bot.send_message(**kwargs)
        logger.info("✅ Daily report sent successfully.")

    except Exception as e:
        # Log the error but DO NOT re-raise — keeps the bot alive
        logger.error(f"❌ Failed to send daily report: {e}", exc_info=True)


# ── Command Handlers ───────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hello! I'm running and stable.\n"
        "Use /help to see available commands."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *Available Commands:*\n"
        "/start  — Start the bot\n"
        "/help   — Show this message\n"
        "/report — Trigger an instant report",
        parse_mode="Markdown",
    )

async def instant_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lets you manually trigger the daily report on demand."""
    await update.message.reply_text("⏳ Sending report...")
    await send_daily_report(context.bot)
    await update.message.reply_text("✅ Done!")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Unknown command. Try /help.")


# ── Startup Validation ─────────────────────────────────────────────────────────
def validate_env():
    """Fail fast on startup if critical variables are missing."""
    missing = []
    if not BOT_TOKEN:
        missing.append("BOT_TOKEN")
    if not MY_CHAT_ID:
        missing.append("MY_CHAT_ID")
    if missing:
        raise EnvironmentError(
            f"❌ Missing required environment variables: {', '.join(missing)}\n"
            "Set them in Railway → your service → Variables tab."
        )


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    validate_env()

    # Build the application
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # ── Register handlers ──────────────────────────────────────────────────────
    application.add_handler(CommandHandler("start",   start))
    application.add_handler(CommandHandler("help",    help_command))
    application.add_handler(CommandHandler("report",  instant_report))
    # Catch-all for unknown commands — must be registered LAST
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # ── Scheduler ─────────────────────────────────────────────────────────────
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        send_daily_report,
        trigger="cron",
        hour=9,        # 09:00 UTC daily — adjust to your timezone
        minute=0,
        args=[application.bot],
        id="daily_report",
        replace_existing=True,      # Prevents duplicate jobs on hot-reload
        misfire_grace_time=3600,    # Run job even if Railway was briefly down
    )
    scheduler.start()
    logger.info("📅 Scheduler started — daily report at 09:00 UTC.")
    logger.info("🚀 Bot is running... Waiting for commands.")

    # ✅ v20+ correct entry point
    # run_polling() manages its own event loop — never wrap with asyncio.run()
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,   # Ignore messages sent while bot was offline
    )


if __name__ == "__main__":
    main()
