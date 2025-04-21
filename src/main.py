import os

from telegram import Update
from telegram.ext import CommandHandler, MessageHandler, filters, ApplicationBuilder, ContextTypes

from chat import handle_message
from commands import set_openai_key_command, set_openai_endpoint_command, set_openai_model_command, set_openai_enable_tools_command, start_command, \
    help_command, subscribe_twitter_user_command, unsubscribe_twitter_user_command, status_command, get_all_subscribed_users_command, set_twitter_translation_command, set_pixiv_translation_command, set_pixiv_direct_translation_command, set_pixiv_streaming_translation_command, \
    set_system_prompt_command, reset_system_prompt_command, show_system_prompt_command, list_twitter_subscription_command, \
    get_redis_command, set_redis_command, del_redis_command, list_redis_command
from core import logger
from tweet import check_for_new_tweets, send_tweets

STOP_TWITTER_SCRAPE = os.getenv('STOP_TWITTER_SCRAPE', 'false').lower() == 'true'
SCRAPE_INTERVAL = int(os.environ.get('SCRAPE_INTERVAL', 300))
SENT_INTERVAL = int(os.environ.get('SENT_INTERVAL', 10))


async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle commmands from channel posts

    The goal is to fix CommandHandler not working for channel posts, we pass the command to the handler
    """
    logger.info(f"Command received: {update.effective_message.text}")

    if not update.effective_message:
        return

    if update.effective_message.text.startswith('/'):
        command = update.effective_message.text[1:].split(' ')[0]
        context.args = update.effective_message.text[1:].split(' ')[1:]
        logger.info(f"Command received: {command}")

        if command == 'start':
            await start_command(update, context)
        elif command == 'help':
            await help_command(update, context)
        elif command == 'status':
            await status_command(update, context)
        elif command == 'set_openai_key':
            await set_openai_key_command(update, context)
        elif command == 'set_openai_endpoint':
            await set_openai_endpoint_command(update, context)
        elif command == 'set_openai_model':
            await set_openai_model_command(update, context)
        elif command == 'set_openai_enable_tools':
            await set_openai_enable_tools_command(update, context)
        elif command == 'set_twitter_translation':
            await set_twitter_translation_command(update, context)
        elif command == 'set_pixiv_translation':
            await set_pixiv_translation_command(update, context)
        elif command == 'set_pixiv_direct_translation':
            await set_pixiv_direct_translation_command(update, context)
        elif command == 'set_pixiv_streaming_translation':
            await set_pixiv_streaming_translation_command(update, context)
        elif command == 'subscribe_twitter_user':
            await subscribe_twitter_user_command(update, context)
        elif command == 'unsubscribe_twitter_user':
            await unsubscribe_twitter_user_command(update, context)
        elif command == 'get_all_subscribed_users':
            await get_all_subscribed_users_command(update, context)
        elif command == 'set_system_prompt':
            await set_system_prompt_command(update, context)
        elif command == 'reset_system_prompt':
            await reset_system_prompt_command(update, context)
        elif command == 'show_system_prompt':
            await show_system_prompt_command(update, context)
        elif command == 'list_twitter_subscription':
            await list_twitter_subscription_command(update, context)
        elif command == 'get_redis':
            await get_redis_command(update, context)
        elif command == 'set_redis':
            await set_redis_command(update, context)
        elif command == 'del_redis':
            await del_redis_command(update, context)
        elif command == 'list_redis':
            await list_redis_command(update, context)


def main() -> None:
    telegram_token = os.getenv('TELEGRAM_TOKEN')
    if not telegram_token:
        logger.error("TELEGRAM_TOKEN environment variable not set")
        raise ValueError("Please set the TELEGRAM_TOKEN environment variable")

    logger.info("Starting bot...")
    app = ApplicationBuilder().token(telegram_token).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("set_openai_key", set_openai_key_command))
    app.add_handler(CommandHandler("set_openai_endpoint", set_openai_endpoint_command))
    app.add_handler(CommandHandler("set_openai_model", set_openai_model_command))
    app.add_handler(CommandHandler("set_openai_enable_tools", set_openai_enable_tools_command))
    app.add_handler(CommandHandler("set_twitter_translation", set_twitter_translation_command))
    app.add_handler(CommandHandler("set_pixiv_translation", set_pixiv_translation_command))
    app.add_handler(CommandHandler("set_pixiv_direct_translation", set_pixiv_direct_translation_command))
    app.add_handler(CommandHandler("set_pixiv_streaming_translation", set_pixiv_streaming_translation_command))
    app.add_handler(CommandHandler("subscribe_twitter_user", subscribe_twitter_user_command))
    app.add_handler(CommandHandler("unsubscribe_twitter_user", unsubscribe_twitter_user_command))
    app.add_handler(CommandHandler("get_all_subscribed_users", get_all_subscribed_users_command))
    app.add_handler(CommandHandler("set_system_prompt", set_system_prompt_command))
    app.add_handler(CommandHandler("reset_system_prompt", reset_system_prompt_command))
    app.add_handler(CommandHandler("show_system_prompt", show_system_prompt_command))
    app.add_handler(CommandHandler("list_twitter_subscription", list_twitter_subscription_command))
    app.add_handler(CommandHandler("get_redis", get_redis_command))
    app.add_handler(CommandHandler("set_redis", set_redis_command))
    app.add_handler(CommandHandler("del_redis", del_redis_command))
    app.add_handler(CommandHandler("list_redis", list_redis_command))
    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POSTS & filters.COMMAND, handle_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    if not STOP_TWITTER_SCRAPE:
        app.job_queue.run_repeating(check_for_new_tweets, interval=SCRAPE_INTERVAL)
        app.job_queue.run_repeating(send_tweets, interval=SENT_INTERVAL)

    logger.info("Bot is ready to accept connections")
    app.run_polling()


if __name__ == '__main__':
    main()
