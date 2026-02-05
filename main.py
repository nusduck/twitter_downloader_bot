import logging
import os
from telegram import BotCommand, BotCommandScopeChat
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    PicklePersistence,
    filters,
)

from app.core.config import config
from app.bot.handlers import (
    start,
    help_command,
    stats_command,
    reset_stats_command,
    handle_message,
    error_handler,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# Set higher logging level for httpx to avoid spamming
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

async def post_init(application):
    """Set up commands after application is initialized."""
    public_commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Help message"),
    ]
    dev_commands = public_commands + [
        BotCommand("stats", "Get bot statistics"),
        BotCommand("resetstats", "Reset bot statistics"),
    ]
    
    await application.bot.set_my_commands(public_commands)
    
    if config.DEVELOPER_ID:
        try:
            await application.bot.set_my_commands(
                dev_commands, 
                scope=BotCommandScopeChat(config.DEVELOPER_ID)
            )
        except Exception as e:
            logger.warning(f"Couldn't set commands for developer: {e}")

def main():
    """Start the bot."""
    # Ensure data directory exists for persistence
    os.makedirs(os.path.dirname(config.PERSISTENCE_PATH), exist_ok=True)
    
    persistence = PicklePersistence(filepath=config.PERSISTENCE_PATH)
    
    builder = ApplicationBuilder().token(config.BOT_TOKEN).persistence(persistence)
    
    # Increase timeouts for large file uploads
    builder.read_timeout(3600).write_timeout(3600).connect_timeout(120)
    
    # Use Local Bot API Server if configured
    if config.BOT_API_BASE_URL:
        logger.info(f"Using Local Bot API Server: {config.BOT_API_BASE_URL}")
        builder.base_url(config.BOT_API_BASE_URL)
        builder.local_mode(True)

    application = builder.post_init(post_init).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command, filters=filters.Chat(config.DEVELOPER_ID)))
    application.add_handler(CommandHandler("resetstats", reset_stats_command, filters=filters.Chat(config.DEVELOPER_ID)))
    
    # Message handler for tweet links
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Error handler
    application.add_error_handler(error_handler)

    logger.info("Bot started. Press Ctrl+C to stop.")
    application.run_polling()

if __name__ == "__main__":
    main()
