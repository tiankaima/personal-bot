import os
from telegram.ext import CommandHandler, MessageHandler, filters, ApplicationBuilder
from commands import set_openai_key, set_openai_endpoint, set_openai_model, start, help_command
from chat import handle_message
from core import logger


def main() -> None:
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    if not telegram_token:
        logger.error("TELEGRAM_TOKEN environment variable not set")
        raise ValueError("Please set the TELEGRAM_TOKEN environment variable")

    logger.info("Starting bot...")
    app = ApplicationBuilder().token(telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("set_openai_key", set_openai_key))
    app.add_handler(CommandHandler("set_openai_endpoint", set_openai_endpoint))
    app.add_handler(CommandHandler("set_openai_model", set_openai_model))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is ready to accept connections")
    app.run_polling()


if __name__ == '__main__':
    main()
