from core import logger, redis_client
from tweet import subscribe_twitter_user, unsubscribe_twitter_user
from telegram import Update
from telegram.ext import CallbackContext


async def start(update: Update, context: CallbackContext) -> None:
    await update.effective_message.reply_text('Hi! Send me a message to start a conversation.\n\nYou can use /help to see the available commands.', reply_to_message_id=update.effective_message.message_id)
    logger.info(f"New conversation started with user {update.effective_message.from_user.id}")


async def help_command(update: Update, context: CallbackContext) -> None:
    await update.effective_message.reply_text("""
    Available commands:
    /set_openai_key <your_openai_api_key>
    /set_openai_endpoint <your_openai_api_endpoint>
    /set_openai_model <your_openai_model>
    /subscribe_twitter_user <twitter_username>
    /unsubscribe_twitter_user <twitter_username>
    """, reply_to_message_id=update.effective_message.message_id)
    logger.debug(f"Help command used by user {update.effective_message.from_user.id}")


async def set_openai_key(update: Update, context: CallbackContext) -> None:
    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text('Usage: /set_openai_key <your_openai_api_key>', reply_to_message_id=update.effective_message.message_id)
        logger.warning(f"Invalid OpenAI key format from user {update.effective_message.from_user.id}")
        return

    openai_api_key = context.args[0]
    await redis_client.set(f"user:{update.effective_message.from_user.id}:openai_api_key", openai_api_key)
    await update.effective_message.reply_text('Your OpenAI API key has been set.', reply_to_message_id=update.effective_message.message_id)
    logger.info(f"OpenAI API key set for user {update.effective_message.from_user.id}")


async def set_openai_endpoint(update: Update, context: CallbackContext) -> None:
    if not context.args or len(context.args) > 1:
        await update.effective_message.reply_text('Usage: /set_openai_endpoint <your_openai_api_endpoint>')
        logger.warning(f"Invalid OpenAI endpoint format from user {update.effective_message.from_user.id}")
        return

    if openai_api_endpoint := context.args[0] if context.args else None:
        await redis_client.set(f"user:{update.effective_message.from_user.id}:openai_api_endpoint", openai_api_endpoint)
        await update.effective_message.reply_text('Your OpenAI API endpoint has been set.', reply_to_message_id=update.effective_message.message_id)
        logger.info(f"OpenAI API endpoint set for user {update.effective_message.from_user.id}: {openai_api_endpoint}")
    else:
        await update.effective_message.reply_text('Usage: /set_openai_endpoint <your_openai_api_endpoint>', reply_to_message_id=update.effective_message.message_id)
        logger.warning(f"Invalid OpenAI endpoint format from user {update.effective_message.from_user.id}")


async def set_openai_model(update: Update, context: CallbackContext) -> None:
    if not context.args or len(context.args) > 1:
        await update.effective_message.reply_text('Usage: /set_openai_model <your_openai_model>')
        logger.warning(f"Invalid OpenAI model format from user {update.effective_message.from_user.id}")
        return

    if openai_model := context.args[0] if context.args else None:
        await redis_client.set(f"user:{update.effective_message.from_user.id}:openai_model", openai_model)
        await update.effective_message.reply_text('Your OpenAI model has been set.', reply_to_message_id=update.effective_message.message_id)
        logger.info(f"OpenAI model set for user {update.effective_message.from_user.id}: {openai_model}")
    else:
        await update.effective_message.reply_text('Usage: /set_openai_model <your_openai_model>', reply_to_message_id=update.effective_message.message_id)
        logger.warning(f"Invalid OpenAI model format from user {update.effective_message.from_user.id}")


async def subscribe_twitter_user_command(update: Update, context: CallbackContext) -> None:
    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text('Usage: /subscribe_twitter_user <twitter_username>', reply_to_message_id=update.effective_message.message_id)
        return
    await subscribe_twitter_user(context.args[0], update.effective_message.chat.id)
    await update.effective_message.reply_text(f'Subscribed to {context.args[0]}', reply_to_message_id=update.effective_message.message_id)
    logger.info(f"Subscribed to {context.args[0]} for user {update.effective_message.chat.id}")


async def unsubscribe_twitter_user_command(update: Update, context: CallbackContext) -> None:
    if not context.args or len(context.args) != 1:
        await update.effective_message.reply_text('Usage: /unsubscribe_twitter_user <twitter_username>', reply_to_message_id=update.effective_message.message_id)
        return
    await unsubscribe_twitter_user(context.args[0], update.effective_message.chat.id)
    await update.effective_message.reply_text(f'Unsubscribed from {context.args[0]}', reply_to_message_id=update.effective_message.message_id)
    logger.info(f"Unsubscribed from {context.args[0]} for user {update.effective_message.from_user.id}")
