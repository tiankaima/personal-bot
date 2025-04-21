import os
from typing import Callable, Coroutine

from telegram import Update
from telegram.ext import CallbackContext

from core import redis_client, logger
from tweet import subscribe_twitter_user, unsubscribe_twitter_user, get_all_subscribed_users
from utils import get_redis_value, admin_required, ADMIN_CHAT_ID_LIST

ADMIN_CHAT_ID_LIST = [int(id) for id in os.getenv('ADMIN_CHAT_ID_LIST', '').split(',') if id]


async def start_command(update: Update, context: CallbackContext) -> None:
    await update.effective_message.reply_text(
        'Hi! Send me a message to start a conversation.\n\nYou can use /help to see the available commands.',
        reply_to_message_id=update.effective_message.message_id)


async def help_command(update: Update, context: CallbackContext) -> None:
    help_text = """
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
/list_twitter_subscription - List all your subscribed Twitter users
/set_system_prompt <your_system_prompt> - Set your custom system prompt
/reset_system_prompt - Reset to default system prompt
/show_system_prompt - Show your current system prompt
"""
    
    if update.effective_chat.id in ADMIN_CHAT_ID_LIST:
        help_text += """
Admin commands:
/get_redis <key> - Get Redis key value
/set_redis <key> <value> - Set Redis key value
/del_redis <key> - Delete Redis key
/list_redis <pattern> - List Redis keys matching pattern
"""
    
    await update.effective_message.reply_text(help_text, reply_to_message_id=update.effective_message.message_id)
    
"""
Send this to BotFather for command autocompletion:

start - Start a conversation with the bot
help - Show available commands
status - Show your current settings and configuration
set_openai_key - <your_openai_api_key> - Set your OpenAI API key
set_openai_endpoint - <your_openai_api_endpoint> - Set your OpenAI API endpoint
set_openai_model - <your_openai_model> - Set your OpenAI model
set_openai_enable_tools - <true/false> - Enable or disable OpenAI tools
set_twitter_translation - <true/false> - Enable or disable Twitter translation
set_pixiv_translation - <true/false> - Enable or disable Pixiv translation
set_pixiv_direct_translation - <true/false> - Enable or disable direct Pixiv translation
set_pixiv_streaming_translation - <true/false> - Enable or disable streaming Pixiv translation
subscribe_twitter_user - <twitter_username> - Subscribe to a Twitter user's updates
unsubscribe_twitter_user - <twitter_username> - Unsubscribe from a Twitter user's updates
get_all_subscribed_users - List all subscribed Twitter users
list_twitter_subscription - List all your subscribed Twitter users
set_system_prompt - <your_system_prompt> - Set your custom system prompt for the AI
reset_system_prompt - Reset to default system prompt
show_system_prompt - Show your current system prompt
"""


async def status_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_message.from_user.id
    chat_id = update.effective_message.chat.id

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
- User ID: {user_id}
- Chat ID: {chat_id}
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

async def set_system_prompt_command(update: Update, context: CallbackContext) -> None:
    if not context.args:
        await update.effective_message.reply_text(
            'Usage: /set_system_prompt <your_system_prompt>',
            reply_to_message_id=update.effective_message.message_id
        )
        return

    user_id = update.effective_message.from_user.id
    system_prompt = ' '.join(context.args)
    await redis_client.set(f"user:{user_id}:system_prompt", system_prompt)
    await update.effective_message.set_reaction("👌")

async def reset_system_prompt_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_message.from_user.id
    await redis_client.delete(f"user:{user_id}:system_prompt")
    await update.effective_message.set_reaction("👌")

async def show_system_prompt_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_message.from_user.id
    system_prompt = await get_redis_value(f"user:{user_id}:system_prompt")
    if not system_prompt:
        system_prompt = "Using default system prompt"
    await update.effective_message.reply_text(
        f"Your current system prompt:\n\n{system_prompt}",
        reply_to_message_id=update.effective_message.message_id
    )

async def list_twitter_subscription_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_message.from_user.id
    subscribed_users = await redis_client.smembers(f"telegram_sub_target:{user_id}")
    
    if not subscribed_users:
        await update.effective_message.reply_text(
            "You are not subscribed to any Twitter users.",
            reply_to_message_id=update.effective_message.message_id
        )
        return
    
    message = "Your subscribed Twitter users:\n\n"
    for username in subscribed_users:
        message += f"• @{username}\n"
    
    await update.effective_message.reply_text(
        message,
        reply_to_message_id=update.effective_message.message_id
    )

@admin_required
async def get_redis_command(update: Update, context: CallbackContext) -> None:
    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text('Usage: /get_redis <key>', reply_to_message_id=update.effective_message.message_id)
        return

    key = context.args[0]
    value = await redis_client.get(key)
    if value is None:
        await update.effective_message.reply_text(f"Key '{key}' not found", reply_to_message_id=update.effective_message.message_id)
    else:
        await update.effective_message.reply_text(f"Key: {key}\nValue: {value}", reply_to_message_id=update.effective_message.message_id)

@admin_required
async def set_redis_command(update: Update, context: CallbackContext) -> None:
    if not context.args or len(context.args) < 2:
        await update.effective_message.reply_text('Usage: /set_redis <key> <value>', reply_to_message_id=update.effective_message.message_id)
        return

    key = context.args[0]
    value = ' '.join(context.args[1:])
    await redis_client.set(key, value)
    await update.effective_message.set_reaction("👌")

@admin_required
async def del_redis_command(update: Update, context: CallbackContext) -> None:
    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text('Usage: /del_redis <key>', reply_to_message_id=update.effective_message.message_id)
        return

    key = context.args[0]
    deleted = await redis_client.delete(key)
    if deleted:
        await update.effective_message.set_reaction("👌")
    else:
        await update.effective_message.reply_text(f"Key '{key}' not found", reply_to_message_id=update.effective_message.message_id)

@admin_required
async def list_redis_command(update: Update, context: CallbackContext) -> None:
    # Get pattern and check for batch mode
    pattern = context.args[0] if context.args else "*"
    is_batch_mode = pattern.startswith(';')
    
    # Remove ; from pattern if in batch mode
    if is_batch_mode:
        pattern = pattern[1:]
    
    keys = await redis_client.keys(pattern)
    
    if not keys:
        await update.effective_message.reply_text(f"No keys found matching pattern '{pattern}'", reply_to_message_id=update.effective_message.message_id)
        return

    if is_batch_mode:
        # In batch mode, send keys in batches of 20
        batch_size = 20
        total_keys = len(keys)
        for i in range(0, total_keys, batch_size):
            batch = keys[i:i + batch_size]
            message = f"Keys matching pattern '{pattern}' (batch {i//batch_size + 1}/{(total_keys-1)//batch_size + 1}):\n\n"
            for key in batch:
                message += f"• {key}\n"
            await update.effective_message.reply_text(message, reply_to_message_id=update.effective_message.message_id)
    else:
        # In normal mode, limit to first 20 keys
        keys = keys[:20]
        message = f"Keys matching pattern '{pattern}' (showing first 20):\n\n"
        for key in keys:
            message += f"• {key}\n"
        
        if len(keys) >= 20:
            message += "\nNote: Showing first 20 keys. Use /list_redis ;<pattern> to see all keys in batches."
        
        await update.effective_message.reply_text(message, reply_to_message_id=update.effective_message.message_id)
