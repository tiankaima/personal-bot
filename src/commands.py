from typing import Callable, Coroutine

from telegram import Update
from telegram.ext import CallbackContext

from core import redis_client, logger
from tweet import subscribe_twitter_user, unsubscribe_twitter_user, get_all_subscribed_users
from utils import get_redis_value


async def start_command(update: Update, context: CallbackContext) -> None:
    await update.effective_message.reply_text(
        'Hi! Send me a message to start a conversation.\n\nYou can use /help to see the available commands.',
        reply_to_message_id=update.effective_message.message_id)


async def help_command(update: Update, context: CallbackContext) -> None:
    await update.effective_message.reply_text("""
Available commands:
/start
/help
/status
/set_openai_key <your_openai_api_key>
/set_openai_endpoint <your_openai_api_endpoint>
/set_openai_model <your_openai_model>
/set_openai_enable_tools <true/false>
/set_twitter_translation <true/false>
/set_pixiv_translation <true/false>
/set_pixiv_direct_translation <true/false>
/set_pixiv_streaming_translation <true/false>
/subscribe_twitter_user <twitter_username>
/unsubscribe_twitter_user <twitter_username>
/get_all_subscribed_users
""", reply_to_message_id=update.effective_message.message_id)


async def status_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_message.from_user.id

    openai_api_key = await get_redis_value(f"user:{user_id}:openai_api_key")
    openai_api_endpoint = await get_redis_value(f"user:{user_id}:openai_api_endpoint")
    openai_model = await get_redis_value(f"user:{user_id}:openai_model")
    openai_enable_tools = await get_redis_value(f"user:{user_id}:openai_enable_tools")
    twitter_translation = await get_redis_value(f"user:{user_id}:twitter_translation", "false")
    pixiv_translation = await get_redis_value(f"user:{user_id}:pixiv_translation", "false")
    pixiv_direct_translation = await get_redis_value(f"user:{user_id}:pixiv_direct_translation", "true")
    pixiv_streaming_translation = await get_redis_value(f"user:{user_id}:pixiv_streaming_translation", "true")

    await update.effective_message.reply_text(f"""
Status:
- OpenAI API key: {openai_api_key}
- OpenAI API endpoint: {openai_api_endpoint}
- OpenAI model: {openai_model}
- OpenAI enable tools: {openai_enable_tools}
- Twitter translation: {twitter_translation}
- Pixiv translation: {pixiv_translation}
- Pixiv direct translation: {pixiv_direct_translation}
- Pixiv streaming translation: {pixiv_streaming_translation}
""", reply_to_message_id=update.effective_message.message_id)


def set_key_command(key: str):
    async def set_key(update: Update, context: CallbackContext) -> None:
        if not context.args or len(context.args) != 1:
            await update.effective_message.reply_text(f'Usage: /set_{key} <your_{key}>',
                                                      reply_to_message_id=update.effective_message.message_id)
            return

        await redis_client.set(f"user:{update.effective_message.from_user.id}:{key}", context.args[0])
        await update.effective_message.set_reaction("👌")

    return set_key


def call_function_with_one_param_command(function: Callable[[str, int], Coroutine]):
    async def call_function(update: Update, context: CallbackContext) -> None:
        if not context.args or len(context.args) != 1:
            await update.effective_message.reply_text(
                f'Usage: /{function.__name__} <twitter_username>',
                reply_to_message_id=update.effective_message.message_id
            )
            return
        try:
            result = await function(context.args[0], update.effective_message.chat.id)

            if result is None:
                await update.effective_message.set_reaction("👌")
            else:
                await update.effective_message.reply_text(
                    result,
                    reply_to_message_id=update.effective_message.message_id
                )
        except Exception as e:
            await update.effective_message.reply_text(
                'Something went wrong!',
                reply_to_message_id=update.effective_message.message_id
            )
            logger.exception(e)

    return call_function


def call_function_command(function: Callable[[int], Coroutine]):
    async def call_function(update: Update, context: CallbackContext) -> None:
        if context.args or len(context.args) != 0:
            await update.effective_message.reply_text(
                f'Usage: /{function.__name__}',
                reply_to_message_id=update.effective_message.message_id
            )
            return

        try:
            result = await function(update.effective_message.chat.id)

            if result is None:
                await update.effective_message.set_reaction("👌")
            else:
                await update.effective_message.reply_text(
                    result,
                    reply_to_message_id=update.effective_message.message_id
                )
        except Exception as e:
            await update.effective_message.reply_text(
                'Something went wrong!',
                reply_to_message_id=update.effective_message.message_id
            )
            logger.exception(e)

    return call_function


set_openai_key_command = set_key_command("openai_api_key")
set_openai_endpoint_command = set_key_command("openai_api_endpoint")
set_openai_model_command = set_key_command("openai_model")
set_openai_enable_tools_command = set_key_command("openai_enable_tools")
set_twitter_translation_command = set_key_command("twitter_translation")
set_pixiv_translation_command = set_key_command("pixiv_translation")
set_pixiv_direct_translation_command = set_key_command('pixiv_direct_translation')
set_pixiv_streaming_translation_command = set_key_command('pixiv_streaming_translation')

subscribe_twitter_user_command = call_function_with_one_param_command(subscribe_twitter_user)
unsubscribe_twitter_user_command = call_function_with_one_param_command(unsubscribe_twitter_user)
get_all_subscribed_users_command = call_function_command(get_all_subscribed_users)
